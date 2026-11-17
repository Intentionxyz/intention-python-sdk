# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import unittest
import httpx
from intention_sdk.api.referral_client import ReferralClient
from intention_sdk.events.referral_events import decode_referral_event_json


class ReservedCodesContract(unittest.IsolatedAsyncioTestCase):
    async def test_queries_canonical_paths_and_preserves_flags(self):
        paths = []
        def response(request):
            paths.append(request.url.path)
            value = dict(code="INTENTION", registered=False, reservedForRegistration=True,
                         availableForRegistration=False, policyRevision="1", asOfBlockHeight="101", sourceSeqId="100000000")
            if request.url.path.endswith("reserved-codes"):
                value = dict(initialized=True, revision="1", active=[], pending=None)
            return httpx.Response(200, json=dict(code=0,data=value,seqId="233333"))
        client = ReferralClient("https://relayer.test",transport=httpx.MockTransport(response))
        try:
            self.assertEqual((await client.get_reserved_codes())["active"], [])
            self.assertFalse((await client.get_code_availability("intention"))["availableForRegistration"])
            self.assertEqual(paths,["/v1/dex/referral/reserved-codes","/v1/dex/referral/codes/INTENTION/availability"])
            with self.assertRaises(ValueError):
                await client.get_code_availability(" INTENTION")
        finally:
            await client.close()

    def test_event_rejects_noncanonical_policy(self):
        value = dict(revision="1",effective_block_height="101",codes=["INTENTION"])
        self.assertEqual(decode_referral_event_json("ReferralReservedCodesUpdatedEvent",value)["revision"],1)
        for codes in (["intention"],["INTENTION","INTENTION"],["INTENTION"]*257):
            with self.assertRaises(ValueError):
                decode_referral_event_json("ReferralReservedCodesUpdatedEvent",dict(value,codes=codes))
