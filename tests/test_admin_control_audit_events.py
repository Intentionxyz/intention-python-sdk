# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import unittest

from intention_sdk.bcs import Serializer
from intention_sdk.events.dex_event_decoder import (
    DexAdminActionInvalidatedEvent,
    DexAdminActionScheduledEvent,
    DexAdminControlPolicyUpdatedEvent,
    DexAdminControlInitializedEvent,
    DexAdminControlCommitteeUpdatedEvent,
    DexAdminControlRoleUpdatedEvent,
    decode_dex_event,
)


def _hex(serializer: Serializer) -> str:
    return "0x" + serializer.to_bytes().hex()


def _put_address(serializer: Serializer, byte: int) -> None:
    serializer.serialize_fixed_bytes(bytes([byte]) * 32)


def _action_fixture(terminal: str) -> str:
    serializer = Serializer()
    serializer.serialize_bytes(bytes([0x11]) * 32)
    serializer.serialize_bytes(bytes([0x22]) * 32)
    serializer.serialize_u8(3)
    serializer.serialize_u64(4)
    _put_address(serializer, 0xAA)
    serializer.serialize_u64(5)
    serializer.serialize_u64(6)
    serializer.serialize_u64(7)
    if terminal != "scheduled":
        serializer.serialize_u64(8)
    if terminal != "expired":
        serializer.serialize_u8(5 if terminal == "executed" else 4)
    return _hex(serializer)


def _invalidated_action_fixture() -> str:
    serializer = Serializer()
    serializer.serialize_bytes(bytes([0x11]) * 32)
    serializer.serialize_bytes(bytes([0x22]) * 32)
    serializer.serialize_u8(3)
    serializer.serialize_u64(4)
    serializer.serialize_u64(5)
    _put_address(serializer, 0xAA)
    serializer.serialize_u64(6)
    serializer.serialize_u64(7)
    serializer.serialize_u64(8)
    serializer.serialize_u64(9)
    return _hex(serializer)


class AdminControlAuditEventTests(unittest.TestCase):
    def test_decodes_every_audit_event_family(self) -> None:
        initialized = Serializer()
        for value in (1, 86_400, 604_800):
            initialized.serialize_u64(value)
        initialized.serialize_bytes(bytes([0x11]) * 32)

        enabled = Serializer()
        enabled.serialize_u64(6)

        fee_config = Serializer()
        fee_config.serialize_bytes(bytes([0x44]) * 32)
        fee_config.serialize_bytes(bytes([0x55]) * 32)
        fee_config.serialize_u64(7)

        role = Serializer()
        role.serialize_bytes(bytes([0x66]) * 32)
        role.serialize_u32_as_uleb128(1)
        role.serialize_u64(9)
        role.serialize_u32(2)
        role.serialize_bytes(bytes([0x77]) * 32)

        committee_golden = (
            "0x200101010101010101010101010101010101010101010101010101010101010101"
            "070000000000000008000000000000002002020202020202020202020202020202"
            "020202020202020202020202020202022003030303030303030303030303030303"
            "030303030303030303030303030303030900000000000000"
        )
        policy_golden = (
            "0x200101010101010101010101010101010101010101010101010101010101010101"
            "010000000000000002000000000000008051010000000000c0a8000000000000"
            "803a09000000000080f403000000000040420f0000000000"
        )
        fixtures = (
            ("AdminControlInitializedEvent", _hex(initialized)),
            ("AdminControlEnabledEvent", _hex(enabled)),
            ("AdminActionScheduledEvent", _action_fixture("scheduled")),
            ("AdminActionExecutedEvent", _action_fixture("executed")),
            ("AdminActionCancelledEvent", _action_fixture("cancelled")),
            ("AdminActionExpiredEvent", _action_fixture("expired")),
            ("AdminActionInvalidatedEvent", _invalidated_action_fixture()),
            ("AdminControlRotatedEvent", committee_golden),
            ("AdminControlPolicyUpdatedEvent", policy_golden),
            ("AdminControlListingSignerSetUpdatedEvent", committee_golden),
            ("FeeSignerSetUpdatedEvent", committee_golden),
            ("FeeConfigUpdatedEvent", _hex(fee_config)),
            ("AdminControlRoleUpdatedEvent", _hex(role)),
        )
        for event_type, data in fixtures:
            with self.subTest(event_type=event_type):
                decoded = decode_dex_event(f"0x1::dex::{event_type}", data)
                self.assertIsNotNone(decoded)
                self.assertEqual(decoded.event_type, event_type)

        scheduled = decode_dex_event(
            "0x1::dex::AdminActionScheduledEvent", _action_fixture("scheduled")
        ).event
        self.assertIsInstance(scheduled, DexAdminActionScheduledEvent)
        self.assertEqual(scheduled.signature_count, 4)
        self.assertEqual(scheduled.proposer, "0x" + "aa" * 32)

        invalidated = decode_dex_event(
            "0x1::dex::AdminActionInvalidatedEvent",
            _invalidated_action_fixture(),
        ).event
        self.assertIsInstance(invalidated, DexAdminActionInvalidatedEvent)
        self.assertEqual(invalidated.signer_epoch, 4)
        self.assertEqual(invalidated.current_signer_epoch, 5)
        self.assertEqual(invalidated.executor, "0x" + "aa" * 32)
        self.assertEqual(invalidated.invalidated_at_secs, 9)

        initialized_event = decode_dex_event(
            "0x1::dex::AdminControlInitializedEvent", _hex(initialized)
        ).event
        self.assertIsInstance(initialized_event, DexAdminControlInitializedEvent)
        self.assertEqual(initialized_event.admin_signer_epoch, 1)
        self.assertEqual(initialized_event.admin_delay_secs, 86_400)
        self.assertEqual(initialized_event.admin_action_expiry_secs, 604_800)
        self.assertEqual(initialized_event.committee_digest, bytes([0x11]) * 32)

        committee = decode_dex_event(
            "0x1::dex::AdminControlRotatedEvent", committee_golden
        ).event
        self.assertIsInstance(committee, DexAdminControlCommitteeUpdatedEvent)
        self.assertEqual(committee.old_committee_digest, bytes([0x02]) * 32)
        self.assertEqual(committee.new_committee_digest, bytes([0x03]) * 32)
        self.assertEqual(committee.executed_at_secs, 9)

        policy = decode_dex_event(
            "0x1::dex::AdminControlPolicyUpdatedEvent", policy_golden
        ).event
        self.assertIsInstance(policy, DexAdminControlPolicyUpdatedEvent)
        self.assertEqual(policy.old_policy_epoch, 1)
        self.assertEqual(policy.new_policy_epoch, 2)
        self.assertEqual(policy.old_admin_delay_secs, 86_400)
        self.assertEqual(policy.new_admin_delay_secs, 43_200)
        self.assertEqual(policy.new_admin_action_expiry_secs, 259_200)

        role_event = decode_dex_event(
            "0x1::dex::AdminControlRoleUpdatedEvent", _hex(role)
        ).event
        self.assertIsInstance(role_event, DexAdminControlRoleUpdatedEvent)
        self.assertEqual(role_event.action, 1)
        self.assertEqual(role_event.role_mask, 9)
        self.assertEqual(role_event.target_count, 2)
        self.assertEqual(role_event.targets_digest, bytes([0x77]) * 32)


if __name__ == "__main__":
    unittest.main()
