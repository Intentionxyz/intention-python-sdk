# Intention DEX examples

See the [integration guide](../docs/simplified-integration-guide.md) for the
supported client APIs. Requires Python 3.9 or later.

## Setup

From the repository root:

```bash
python -m pip install '.[examples]'
```

For network examples, configure your node, relayer and a funded test account:

```env
INTENTION_NETWORK=custom
INTENTION_NODE_URL=http://127.0.0.1:8080/v1
INTENTION_FAUCET_URL=http://127.0.0.1:8081
DEX_REST_API_URL=http://127.0.0.1:3000
PRIVATE_KEY=<hex-encoded secp256k1 private key>
TEST_SYMBOL_ID=1
TEST_ASSET_ID=0
TEST_SUBACCOUNT_ID=1
```

Use the endpoint URLs and market and asset IDs supplied by your network.
DEX trading requires collateral; the native-coin faucet does not fund USDC.

## Offline examples

```bash
python dex-examples/15_dex_event_decoding.py
python dex-examples/16_sdk_public_api_smoke.py
python dex-examples/e2e_intention_test.py --lane json-coverage
```

These commands use local fixtures or captured HTTP requests and do not require a
running node. Run the unit tests with:

```bash
python -m unittest discover -t . -s tests -p 'test_*.py'
```

## Network examples

Run `python dex-examples/<file>.py` after configuring the target network.

| File | Purpose |
| --- | --- |
| `01_account_management.py` | Account creation and key import; runs offline |
| `03_standard_transfer.py` | Native-coin and token transfers |
| `04_dex_place_order.py` | Limit and market orders |
| `05_dex_cancel_order.py` | Order cancellation; set `ORDER_ID` |
| `06_dex_replace_order.py` | Order replacement; set `ORDER_ID` |
| `07_dex_batch_orders.py` | Batch order submission |
| `08_dex_user_config.py` | Leverage, position mode and margin mode |
| `09_dex_transfer.py` | Subaccount and cross-chain transfers |
| `11_dex_agent_wallet.py` | Agent approval, trading and revocation |
| `12_vault_operations.py` | Vault queries and transactions |
| `14_dex_rest_queries.py` | DEX REST queries |
| `18_unified_client_usage.py` | Import `trade(signer)` with a funded account |
