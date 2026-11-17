# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import json
import pathlib
import unittest
from types import SimpleNamespace
import httpx

from intention_sdk.api.referral_client import ReferralClient
from intention_sdk.events.referral_events import decode_referral_event_bytes, decode_referral_event_json
from intention_sdk.events.dex_event_decoder import decode_dex_event
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.api.dex_executor import SubmitOptions
from intention_sdk.transactions.dex_payloads import MultiSigProof, ReferralParameters


class ReferralEventContract(unittest.TestCase):
    def test_claimall_total_claimed_keeps_u64_precision(self):
        payload = dict(master="0x1", amount="1", total_claimed=str(2**64 - 1))
        decoded = decode_referral_event_json("ReferralRewardsClaimedEvent", payload)
        self.assertEqual(decoded["total_claimed"], 2**64 - 1)
        self.assertEqual(decoded["amount"], 1)
        self.assertNotIn("sources", decoded)
        payload["total_claimed"] = str(2**64)
        with self.assertRaises(ValueError):
            decode_referral_event_json("ReferralRewardsClaimedEvent", payload)

    def test_chain_vectors_and_strict_consumption(self):
        path = pathlib.Path(__file__).parent / "testdata/referral_events_v1.json"
        vectors = json.loads(path.read_text())
        for name, hex_data in vectors.items():
            data = bytes.fromhex(hex_data)
            self.assertIsNotNone(decode_referral_event_bytes(name, data))
            self.assertEqual(decode_dex_event(f"0x1::dex::{name}", hex_data).event_type, name)
            with self.assertRaises(Exception):
                decode_referral_event_bytes(name, data + b"\x00")
            with self.assertRaises(Exception):
                decode_referral_event_bytes(name, data[:-1])
        fee = decode_referral_event_bytes("DexReferralFeeEvent", bytes.fromhex(vectors["DexReferralFeeEvent"]))
        self.assertEqual(fee["discount"], 450_000)
        self.assertEqual(fee["commission"], 1_080_000)

class ReferralClientContract(unittest.IsolatedAsyncioTestCase):
    async def test_invitee_sort_fields_directions_and_paging(self):
        requests = []
        data = dict(items=[dict(master="0x2", timeJoined=None,
                               volumeSinceBound="9007199254740993.000001",
                               feePaid="2.500000", commissionAccrued="0.250000")],
                    totalCount=21, nextCursor="opaque+/=", asOfBlockHeight="104", sourceSeqId="13000000")

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json=dict(code=0, data=data))

        client = ReferralClient("https://relayer.test/v1", transport=httpx.MockTransport(respond))
        try:
            for by in ("timeJoined", "volumeSinceBound", "feePaid", "commissionAccrued"):
                for direction in ("asc", "desc"):
                    for paging in (dict(page=3), dict(cursor="opaque+/=")):
                        result = await client.get_invitees("0x1", limit=10, sort_by=by, sort_order=direction, **paging)
                        self.assertEqual(result, data)
                        query = requests[-1].url.params
                        self.assertEqual(query["sortBy"], by)
                        self.assertEqual(query["sortOrder"], direction)
                        self.assertEqual(query["limit"], "10")
                        self.assertEqual(query.get("page"), "3" if "page" in paging else None)
                        self.assertEqual(query.get("cursor"), paging.get("cursor"))
            await client.get_invitees("0x1")
            self.assertNotIn("sortBy", requests[-1].url.params)
            self.assertNotIn("sortOrder", requests[-1].url.params)
            await client.get_invitees("0x1", sort_by="feePaid")
            self.assertNotIn("sortOrder", requests[-1].url.params)
            await client.get_invitees("0x1", sort_order="asc")
            self.assertNotIn("sortBy", requests[-1].url.params)
            before = len(requests)
            for bad in (dict(sort_by="volume"), dict(sort_by=""), dict(sort_order="ASC"), dict(sort_order="")):
                with self.assertRaisesRegex(ValueError, "sort"):
                    await client.get_invitees("0x1", **bad)
            with self.assertRaisesRegex(ValueError, "Referral page"):
                await client.get_invitees("0x1", page=1, cursor="opaque", sort_by="feePaid")
            for method in (client.get_claims, client.get_sources, client.get_fills):
                with self.assertRaises(TypeError):
                    await method("0x1", sort_by="feePaid")
            self.assertEqual(len(requests), before)
        finally:
            await client.close()

    async def test_claimall_preflight_checks_gate_and_full_balance(self):
        config = dict(gateActive=False, active=dict(minClaimAmountQuantums="1000000"))
        requested = []

        def respond(request):
            requested.append(request.url.path)
            data = config if request.url.path.endswith("/config") else dict(claimableQuantums="999999")
            return httpx.Response(200, json=dict(code=0, data=data))

        client = ReferralClient("https://relayer.test", transport=httpx.MockTransport(respond))
        try:
            with self.assertRaisesRegex(ValueError, "not active"):
                await client.build_claim("0x1", 1)
            self.assertEqual(len(requested), 1)
            config["gateActive"] = True
            with self.assertRaisesRegex(ValueError, "minimum"):
                await client.build_claim("0x1", 1)
            self.assertEqual(len(requested), 3)
            self.assertFalse(any(path.endswith("/sources") for path in requested))
        finally:
            await client.close()

    async def test_code_lookup_uses_canonical_case_and_does_not_aggregate(self):
        requests = []

        def respond(request):
            requests.append(request)
            if request.url.path.endswith("/MISSING"):
                return httpx.Response(404)
            return httpx.Response(200, json=dict(code=0, data=dict(
                code="ABC123", referrer="0x" + "0" * 63 + "1",
                asOfBlockHeight="104", sourceSeqId="13000000",
            )))

        client = ReferralClient(
            "https://relayer.test/v1", transport=httpx.MockTransport(respond)
        )
        try:
            result = await client.resolve_code("AbC123")
            self.assertEqual(result["code"], "ABC123")
            self.assertEqual(result["sourceSeqId"], "13000000")
            self.assertEqual(len(requests), 1)
            self.assertEqual(
                requests[0].url.path, "/v1/dex/referral/codes/ABC123"
            )
            for code in ["short", "ABC_12", " ABC123", "a" * 21]:
                with self.assertRaises(ValueError):
                    await client.resolve_code(code)
            self.assertEqual(len(requests), 1)
            with self.assertRaises(httpx.HTTPStatusError):
                await client.resolve_code("MISSING")
        finally:
            await client.close()

    async def test_actions_preserve_proof_and_options_through_executor(self):
        calls = []

        class Executor:
            async def execute_orderless(self, transaction, *, options):
                calls.append((transaction, options))
                return {"success": True}

        def respond(request):
            data = (
                dict(gateActive=True, active=dict(minClaimAmountQuantums="1000000"))
                if request.url.path.endswith("/config")
                else dict(claimableQuantums="1080000")
            )
            return httpx.Response(200, json=dict(code=0, data=data))

        client = ReferralClient(
            "https://relayer.test", executor=Executor(),
            signer=SimpleNamespace(account_address="0x1"),
            transport=httpx.MockTransport(respond),
        )
        try:
            options = SubmitOptions(encoding="json", max_gas_amount=9000)
            await client.register_code("ABC123", 1, options)
            await client.bind_referrer("ABC123", 2, options)
            await client.claim(3, on_behalf_of="0x1", options=options)
            self.assertEqual(
                calls[-1][0].inner.on_behalf_of,
                AccountAddress.from_str_relaxed("0x1"),
            )
            proof = MultiSigProof(bytes(32), 1800000000, [])
            parameters = ReferralParameters(
                40000, 100000, 1000000000, 25000000000,
                1000000000000000, 1000000,
            )
            await client.set_config(parameters, 4, proof, options)
            transaction, forwarded = calls[-1]
            self.assertIs(transaction.multi_sig_proof, proof)
            self.assertEqual(forwarded.encoding, "bcs")
            self.assertEqual(forwarded.max_gas_amount, 9000)
            self.assertEqual(options.encoding, "json")
            self.assertEqual(len(calls), 4)
        finally:
            await client.close()

    async def test_all_queries_and_claimall(self):
        requests = []
        def respond(request):
            requests.append(request)
            if request.url.path.endswith("/config"):
                data = dict(gateActive=True, active=dict(minClaimAmountQuantums="1000000"))
            elif request.url.path.endswith("/sources"):
                raise AssertionError("ClaimAll must not query sources")
            elif request.url.path.endswith("/referrals"):
                data = dict(items=[dict(master="0x1", timeJoined=100, volumeSinceBound="1.000000",
                                        feePaid="2.500000", commissionAccrued="0.250000")],
                            totalCount=1, nextCursor="", asOfBlockHeight="104", sourceSeqId="13000000")
            elif request.url.path.endswith("/claims"):
                data = dict(items=[], totalCount=3, nextCursor="", asOfBlockHeight="104", sourceSeqId="13000000")
            else:
                data = dict(items=[], claimableQuantums="1080000", nextCursor="", asOfBlockHeight="104", sourceSeqId="13000000")
            return httpx.Response(200, json=dict(code=0, data=data, seqId="233333"))
        client = ReferralClient("https://relayer.test/v1", transport=httpx.MockTransport(respond))
        try:
            await client.get_overview("0x1")
            invitees = await client.get_invitees("0x1", limit=2, cursor="opaque")
            self.assertEqual(invitees["totalCount"], 1)
            self.assertEqual(invitees["items"][0]["feePaid"], "2.500000")
            direct_invitees = await client.get_invitees("0x1", limit=10, page=3)
            self.assertEqual(direct_invitees["totalCount"], 1)
            self.assertEqual(requests[-1].url.params["page"], "3")
            with self.assertRaisesRegex(ValueError, "Referral page"):
                await client.get_invitees("0x1", page=0)
            with self.assertRaisesRegex(ValueError, "Referral page"):
                await client.get_invitees("0x1", page=2, cursor="opaque")
            claims = await client.get_claims("0x1", limit=10, page=3)
            self.assertEqual(claims["totalCount"], 3)
            self.assertEqual(requests[-1].url.params["page"], "3")
            self.assertEqual(requests[-1].url.params["limit"], "10")
            with self.assertRaisesRegex(ValueError, "Referral page"):
                await client.get_claims("0x1", page=0)
            with self.assertRaisesRegex(ValueError, "Referral page"):
                await client.get_claims("0x1", page=2, cursor="opaque")
            await client.get_claims("0x1", cursor="opaque")
            self.assertEqual(requests[-1].url.params["cursor"], "opaque")
            await client.get_fills("0x1")
            tx = await client.build_claim("0x1", 123)
            self.assertEqual(tx.inner.nonce, 123)
            self.assertFalse(hasattr(tx.inner, "amount"))
            self.assertFalse(hasattr(tx.inner, "sources"))
            self.assertNotIn("order", requests[-1].url.params)
            self.assertTrue(all(r.url.path.startswith("/v1/dex/referral/") for r in requests))
            self.assertEqual(client.build_register_code("ABC123", 123).inner.payload.nonce, 123)
            self.assertEqual(client.build_bind_referrer("ABC123", 123).inner.payload.nonce, 123)
            with self.assertRaises(TypeError):
                await client.build_claim("0x1", "0.1", 1)
        finally:
            await client.close()
