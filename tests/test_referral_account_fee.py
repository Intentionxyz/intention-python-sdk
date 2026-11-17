# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import json
import pathlib
import unittest
from intention_sdk.events.dex_event_decoder import decode_dex_event, decode_dex_event_data, is_dex_event
from intention_sdk.events.referral_events import decode_referral_event_json

class ReferralAccountFeeTest(unittest.TestCase):
    def test_account_fee_bcs_and_native_json_are_equivalent(self):
        vectors=json.loads((pathlib.Path(__file__).parent/"testdata/referral_fee_event.json").read_text())
        name="0x1::dex::DexReferralFeeEvent"
        self.assertTrue(is_dex_event(name))
        decoded=decode_dex_event(name,vectors["DexReferralFeeEvent"])
        self.assertIsNotNone(decoded)
        value=decoded.event
        self.assertEqual(value["discount"],450000)
        self.assertEqual(value["commission"],1080000)
        self.assertEqual(len(value["master"]),42)
        body={key:str(item) if isinstance(item,int) and key!="symbol_id" else item for key,item in value.items()}
        self.assertEqual(decode_dex_event_data(name,body).event,value)
        self.assertIsNone(decode_dex_event(name,vectors["DexReferralFeeEvent"]+"00"))
        with self.assertRaises(ValueError):
            decode_referral_event_json("DexReferralFeeEvent",dict(body,discount="18446744073709551616"))

    def test_v1_vectors_support_source_json_without_address_projection(self):
        from intention_sdk.events.referral_events import decode_referral_event_bytes
        vectors=json.loads((pathlib.Path(__file__).parent/"testdata/referral_events_v1.json").read_text())
        for name,hex_value in vectors.items():
            value=decode_referral_event_bytes(name,bytes.fromhex(hex_value))
            self.assertEqual(decode_referral_event_json(name,value),value)
