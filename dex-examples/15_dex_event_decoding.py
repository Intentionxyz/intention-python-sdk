# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from pprint import pprint

from intention_sdk import (
    Hex,
    decode_account_transfer_event,
    decode_dex_event,
    decode_transaction_events,
    hex_to_ascii_string,
    is_dex_event,
)
from intention_sdk.events.dex_event_decoder import (
    DexAdlExecutionEvent,
    DexLiquidationDirectAdlEvent,
    validate_adl_execution_event_chunks,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = REPO_ROOT / "tests" / "test_fixtures" / "phase3_event_parity.json"
ADL_FIXTURE_PATH = (
    REPO_ROOT / "tests" / "test_fixtures" / "adl_v5_event_contract.json"
)


def load_fixture(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def main() -> None:
    fixtures = load_fixture(FIXTURE_PATH)
    print("Mode: offline verification example (event decoding)")
    print(
        "Uses checked-in phase3_event_parity.json fixtures and intention_sdk public imports only."
    )
    print()

    single_fixture = fixtures["single_events"]["decode_account_transfer_event"]
    single_decoded = decode_account_transfer_event(bytes.fromhex(single_fixture["hex"]))
    print("Single-event decode: decode_account_transfer_event")
    pprint(single_decoded)
    print()

    unified_fixture = fixtures["unified_events"]["decoded"]["fill_event"]
    print("Unified decode: decode_dex_event")
    print("Known tag:", is_dex_event(unified_fixture["type"]))
    pprint(decode_dex_event(unified_fixture["type"], unified_fixture["data"]))
    print()

    print("Batch decode: decode_transaction_events")
    batch_decoded = decode_transaction_events(
        fixtures["unified_events"]["mixed_batch"]["events"]
    )
    pprint(batch_decoded)
    print()

    adl_fixture = load_fixture(ADL_FIXTURE_PATH)
    adl_decoded = decode_transaction_events(adl_fixture["events"])
    direct = next(
        item.event
        for item in adl_decoded
        if isinstance(item.event, DexLiquidationDirectAdlEvent)
    )
    execution_chunks = tuple(
        item.event
        for item in adl_decoded
        if isinstance(item.event, DexAdlExecutionEvent)
    )
    validate_adl_execution_event_chunks(execution_chunks)
    execution = execution_chunks[0]
    source = adl_fixture["source"]
    print(
        "ADL v5 source:",
        f"{source['origin']}",
        f"({source['case']})",
    )
    print(
        "ADL mixed batch:",
        [(item.index, item.event_type) for item in adl_decoded],
    )
    print(
        "Direct ADL source:",
        f"block={direct.block_height}",
        f"action_seq={direct.action_seq}",
        f"flow=0x{direct.flow_instance_id.hex()}",
    )
    print(
        "Execution identity:",
        (
            execution.adl_event_id.trigger_block_height,
            execution.adl_event_id.trigger_index_in_block,
        ),
    )
    print(
        "Chunk metadata:",
        [
            (
                chunk.chunk_index,
                chunk.total_chunks,
                chunk.audit_entries_start_index,
                chunk.audit_entries_end_index_exclusive,
            )
            for chunk in execution_chunks
        ],
    )
    print(
        "Executed audit entries:",
        [
            (entry.audit_entry_index, entry.executed_quantums)
            for chunk in execution_chunks
            for entry in chunk.audit_entries
            if entry.executed_quantums > 0
        ],
    )
    print()

    hex_input = fixtures["helper_vectors"]["hex_prefixed"]["input"]
    ascii_input = fixtures["helper_vectors"]["hex_ascii"]["input"]
    print("Hex helper surface")
    print("Normalized:", Hex.hex_input_to_string(hex_input))
    print("Without prefix:", Hex.hex_input_to_string_without_prefix(hex_input))
    print("ASCII:", hex_to_ascii_string(ascii_input))


if __name__ == "__main__":
    main()
