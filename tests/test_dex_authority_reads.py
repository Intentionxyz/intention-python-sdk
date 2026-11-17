# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""The two multisig reads: what controls an account, and whether an id was spent.

Both are answers a caller acts on with money, and both have an answer that is easy
to mistake for a failure -- an account with no authority record, and an operation
id nobody ever submitted. So the cases below are mostly about those two.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any, Dict, List

import httpx

from intention_sdk.api.dex_account_client import DexAccountClient, DexAuthority

POLICY_RECORD: Dict[str, Any] = {
    "account": "0x0000000000000000000000001111111111111111111111111111111111111111",
    "version": 1,
    "epoch": 3,
    "updated_at_secs": 1_700_000_500,
    "kind": "policy",
    "threshold": 2,
    "owner_count": 3,
    "owners": [
        "0xa1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
        "0xa2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2",
        "0xa3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3",
    ],
    "owners_digest": "0x722e732621398d7da39e5660da787eac27341e74a86b5bb111a8e17dbd45b1a6",
    "created_at_secs": 1_700_000_000,
}


def _client(responses: Dict[str, httpx.Response], seen: List[str]) -> DexAccountClient:
    """A client whose transport answers from a path table and records what was asked."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path not in responses:
            raise AssertionError(f"unexpected request: {request.url.path}")
        return responses[request.url.path]

    return DexAccountClient(
        "http://node.invalid", transport=httpx.MockTransport(handler)
    )


def _run(coro):
    return asyncio.run(coro)


class DexAuthorityReadTest(unittest.TestCase):
    def test_a_policy_record_is_parsed_whole(self) -> None:
        seen: List[str] = []
        client = _client(
            {"/dex/authority/0x11": httpx.Response(200, json=POLICY_RECORD)}, seen
        )

        authority = _run(client.get_authority("0x11"))

        assert authority is not None
        self.assertEqual(authority.kind, "policy")
        self.assertEqual(authority.epoch, 3)
        self.assertEqual(authority.threshold, 2)
        self.assertEqual(len(authority.owners or []), 3)
        self.assertEqual(authority.owners_digest, POLICY_RECORD["owners_digest"])
        # A key account's field stays absent rather than arriving as zero bytes.
        self.assertIsNone(authority.auth_key)
        self.assertEqual(seen, ["/dex/authority/0x11"])

    def test_no_record_reads_as_none_rather_than_raising(self) -> None:
        """The default answer, and the one that must not look like a failure.

        An account with no record is controlled by the key its address derives
        from, which is every account that has never run a multisig operation. The
        node says so with a 404; raising there would make an ordinary account
        indistinguishable from an unreachable node.
        """
        seen: List[str] = []
        client = _client(
            {
                "/dex/authority/0x22": httpx.Response(
                    404, json={"message": "No authority record for 0x22"}
                )
            },
            seen,
        )

        self.assertIsNone(_run(client.get_authority("0x22")))

    def test_a_key_record_reports_the_named_key_and_keeps_its_epoch(self) -> None:
        record = {
            "account": "0x0000000000000000000000002222222222222222222222222222222222222222",
            "version": 1,
            "epoch": 7,
            "updated_at_secs": 1_700_001_000,
            "kind": "key",
            "auth_key": "0x" + "5c" * 32,
        }
        client = _client({"/dex/authority/0x22": httpx.Response(200, json=record)}, [])

        authority = _run(client.get_authority("0x22"))

        assert authority is not None
        self.assertEqual(authority.kind, "key")
        self.assertEqual(authority.auth_key, record["auth_key"])
        # Not restarted at one by leaving a policy: the next Install has to name 8.
        self.assertEqual(authority.epoch, 7)
        self.assertIsNone(authority.owners)

    def test_a_record_this_build_cannot_classify_is_refused(self) -> None:
        # "Who controls this account" is the one question this read exists to
        # answer exactly, so an unknown kind is an error rather than a record
        # rendered under a guess.
        client = _client(
            {
                "/dex/authority/0x33": httpx.Response(
                    200, json={**POLICY_RECORD, "kind": "something_new"}
                )
            },
            [],
        )

        with self.assertRaises(ValueError):
            _run(client.get_authority("0x33"))

    def test_from_json_is_the_whole_parse(self) -> None:
        # The read is a transport plus this function, so the function is worth
        # exercising on its own: a caller holding a record from somewhere else
        # (a log, a fixture) gets the same object.
        authority = DexAuthority.from_json(json.loads(json.dumps(POLICY_RECORD)))
        self.assertEqual(authority.account, POLICY_RECORD["account"])
        self.assertEqual(authority.created_at_secs, 1_700_000_000)


class MultisigOperationReadTest(unittest.TestCase):
    def test_a_spent_operation_reads_as_used(self) -> None:
        op_id = "0x" + "11" * 32
        seen: List[str] = []
        client = _client(
            {
                f"/dex/multisig/op/{op_id}": httpx.Response(
                    200, json={"op_id": op_id, "used": True}
                )
            },
            seen,
        )

        self.assertTrue(_run(client.is_multisig_operation_used(op_id)))
        self.assertEqual(seen, [f"/dex/multisig/op/{op_id}"])

    def test_an_id_never_submitted_reads_as_unused(self) -> None:
        # Not an error and not a 404: `used: false` is the answer for every
        # well-formed id, including one nobody ever signed.
        op_id = "0x" + "22" * 32
        client = _client(
            {
                f"/dex/multisig/op/{op_id}": httpx.Response(
                    200, json={"op_id": op_id, "used": False}
                )
            },
            [],
        )

        self.assertFalse(_run(client.is_multisig_operation_used(op_id)))

    def test_raw_bytes_are_accepted_as_an_operation_id(self) -> None:
        # `multisig_operation_id` returns bytes, so the read takes them without
        # making every caller hex-encode first.
        op_id = bytes([0x33]) * 32
        seen: List[str] = []
        client = _client(
            {
                "/dex/multisig/op/0x" + op_id.hex(): httpx.Response(
                    200, json={"op_id": "0x" + op_id.hex(), "used": True}
                )
            },
            seen,
        )

        self.assertTrue(_run(client.is_multisig_operation_used(op_id)))
        self.assertEqual(seen, ["/dex/multisig/op/0x" + op_id.hex()])

    def test_a_response_without_the_flag_is_refused(self) -> None:
        # Absence of `used` is not "unused": a caller that read it that way would
        # resubmit a withdrawal that may already have gone through.
        op_id = "0x" + "44" * 32
        client = _client(
            {f"/dex/multisig/op/{op_id}": httpx.Response(200, json={"op_id": op_id})},
            [],
        )

        with self.assertRaises(ValueError):
            _run(client.is_multisig_operation_used(op_id))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
