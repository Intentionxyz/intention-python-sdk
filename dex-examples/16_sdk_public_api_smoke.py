# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from intention_sdk import (
    AccountAddress,
    DexTransferTx,
    Hex,
    decode_dex_event,
    decode_transaction_events,
    derive_subaccount_address,
    hex_to_ascii_string,
)
from intention_sdk.bcs import Deserializer, Serializer

REPO_ROOT = Path(__file__).resolve().parent.parent
PHASE1_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "test_fixtures" / "phase1_protocol_parity.json"
)
PHASE2_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "test_fixtures" / "phase2_subaccount_parity.json"
)
PHASE3_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "test_fixtures" / "phase3_event_parity.json"
)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _serialize_hex(payload: object) -> str:
    serializer = Serializer()
    payload.serialize(serializer)
    return serializer.to_bytes().hex()


def main() -> None:
    phase1 = _load_json(PHASE1_FIXTURE_PATH)
    phase2 = _load_json(PHASE2_FIXTURE_PATH)
    phase3 = _load_json(PHASE3_FIXTURE_PATH)

    print("Mode: offline SDK public API smoke")
    print(
        "Uses checked-in phase1/phase2/phase3 fixtures to verify the Intention "
        "SDK public surface."
    )
    print()

    transfer_fixture = phase1["cross_transfer_with_bridge_proof"]
    transfer_tx = DexTransferTx.deserialize(
        Deserializer(bytes.fromhex(transfer_fixture["hex"]))
    )
    assert _serialize_hex(transfer_tx) == transfer_fixture["hex"]

    print("Phase 1 parity: transfer")
    print("  Transfer variant:", transfer_tx.variant.name)
    print()

    derive_fixture = phase2["derive_subaccount_address_seven"]
    derived_subaccount = derive_subaccount_address(
        AccountAddress.from_str(derive_fixture["inputs"]["main_address"]),
        int(derive_fixture["inputs"]["number"]),
    )
    assert derived_subaccount.to_string_long() == derive_fixture["expected"]["address"]

    print("Phase 2 subaccount: address derivation")
    print("  Derived subaccount:", derived_subaccount)
    print()

    unified_fixture = phase3["unified_events"]["decoded"]["fill_event"]
    decoded_event = decode_dex_event(unified_fixture["type"], unified_fixture["data"])
    assert decoded_event is not None
    decoded_batch = decode_transaction_events(
        phase3["unified_events"]["mixed_batch"]["events"]
    )
    assert decoded_batch

    hex_input = phase3["helper_vectors"]["hex_prefixed"]["input"]
    ascii_input = phase3["helper_vectors"]["hex_ascii"]["input"]

    print("Phase 3 events: unified decoding + helpers")
    print("  Event type:", decoded_event.event_type)
    print("  Batch size:", len(decoded_batch))
    print("  Normalized:", Hex.hex_input_to_string(hex_input))
    print("  Without prefix:", Hex.hex_input_to_string_without_prefix(hex_input))
    print("  ASCII:", hex_to_ascii_string(ascii_input))


if __name__ == "__main__":
    main()
