# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
01 - Account Management Test

Covers: Account.generate(),
      Secp256k1PrivateKey, AccountAddress.from_str()
Network: Offline (no network connection required)

Run: python dex-examples/01_account_management.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from intention_sdk.core.account import Secp256k1PrivateKey
from intention_sdk.core.account import Account
from intention_sdk.core.account_address import AccountAddress


def print_header(title: str) -> None:
    print(f"\n===== {title} =====")


def main():
    print("====================================")
    print("  01 - Account Management Test (Offline)")
    print("====================================")

    # 1. Generate Secp256k1 account (EVM compatible)
    print_header("1. Generate Secp256k1 Account")
    secp256k1_account = Account.generate()
    print("Address:", secp256k1_account.account_address)
    print("Signing scheme: Secp256k1")
    print("Private key:", secp256k1_account.private_key.hex())

    # 2. Randomly generate Secp256k1 private key
    print_header("2. Randomly Generate Secp256k1 Private Key")
    random_key = Secp256k1PrivateKey.generate()
    random_pub = random_key.public_key()
    evm_bytes = random_pub.to_evm_account_bytes()
    random_account = Account(AccountAddress(evm_bytes), random_key)
    print("Private key:", random_key.hex())
    print("Address:", random_account.account_address)

    # 3. Import account from hex private key
    print_header("3. Import Account from Hex Private Key")
    hex_key = secp256k1_account.private_key.hex()
    imported_key = Secp256k1PrivateKey.from_hex(hex_key)
    imported_pub = imported_key.public_key()
    imported_evm = imported_pub.to_evm_account_bytes()
    imported_account = Account(AccountAddress(imported_evm), imported_key)
    print("Original address:", secp256k1_account.account_address)
    print("Imported address:", imported_account.account_address)
    print(
        "Address match:",
        str(secp256k1_account.account_address) == str(imported_account.account_address),
    )

    # 4. AccountAddress.from_str() address conversion
    print_header("4. AccountAddress.from_str() Address Conversion")

    # Standard Move address format
    addr1 = AccountAddress.from_str("0x1")
    print("Standard address:", addr1)

    # EVM format address (20 bytes)
    evm_addr = "0x72cd7764075ab7141284143f7cf4e4ef5ef065b7"
    padded_hex = "0x" + evm_addr[2:].zfill(64)
    addr2 = AccountAddress.from_str(padded_hex)
    print("EVM address:", addr2)

    # Manual padding
    addr3 = AccountAddress.from_str(padded_hex)
    print("Padded address:", addr3)

    # 5. Private key export and restore verification
    print_header("5. Private Key Export and Restore Verification")
    original = Account.generate()
    exported_key = original.private_key.hex()
    restored_key = Secp256k1PrivateKey.from_hex(exported_key)
    restored_pub = restored_key.public_key()
    restored_evm = restored_pub.to_evm_account_bytes()
    restored = Account(AccountAddress(restored_evm), restored_key)
    print("Export-restore consistency:")
    print(
        "  Address match:",
        str(original.account_address) == str(restored.account_address),
    )
    print(
        "  Private key match:",
        original.private_key.hex() == restored.private_key.hex(),
    )

    print("\n===== All tests completed =====")


if __name__ == "__main__":
    main()
