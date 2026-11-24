# Intention DEX examples

Requires Python 3.9 or later. Install from the repository root with
`python -m pip install '.[examples]'`.

## TypeScript SDK counterparts

| TypeScript example | Python example |
| --- | --- |
| [account-client-usage.ts](https://github.com/Intentionxyz/intention-ts-sdk/blob/main/examples/account-client-usage.ts) | [account_client_usage.py](account_client_usage.py) |
| [unified-client-usage.ts](https://github.com/Intentionxyz/intention-ts-sdk/blob/main/examples/unified-client-usage.ts) | [18_unified_client_usage.py](18_unified_client_usage.py) |
| [e2e-order-lifecycle.ts](https://github.com/Intentionxyz/intention-ts-sdk/blob/main/examples/e2e-order-lifecycle.ts) | [e2e_order_lifecycle.py](e2e_order_lifecycle.py) |

See the [integration guide](../docs/simplified-integration-guide.md) for the
corresponding client APIs.

## Offline examples

```bash
python dex-examples/01_account_management.py
python dex-examples/15_dex_event_decoding.py
python dex-examples/16_sdk_public_api_smoke.py
python dex-examples/e2e_intention_test.py --lane json-coverage
DRY_RUN=1 python dex-examples/e2e_order_lifecycle.py
```

The lifecycle dry run builds the bracket order payload. The JSON coverage lane
captures signed submissions on a loopback server without broadcasting them.

## Market queries

Set `DEX_REST_API_URL` to your relayer's base URL.

```bash
DEX_REST_API_URL=http://127.0.0.1:3000 \
SYMBOL=BTC-USDC \
python dex-examples/14_dex_rest_queries.py
```

Use `resolution=1m` for minute candles. `limit` is the maximum number of bars
returned for the available history. Set `ACCOUNT_ADDRESS` for account reads.
Set `INTENTION_NODE_URL` for fullnode reads and `TX_HASH` to look up a confirmed
transaction.

## Signed examples

Use a funded, disposable account on your development network. Trade examples
need USDC collateral, and market orders need liquidity on the other side of the
book. Subaccount creation needs an activated main account that meets the
chain's 100,000 USDC trading-volume requirement.

```env
INTENTION_NODE_URL=http://127.0.0.1:8080/v1
DEX_REST_API_URL=http://127.0.0.1:3000
INTENTION_FAUCET_URL=http://127.0.0.1:8081
PRIVATE_KEY=<hex secp256k1 test key>
SYMBOL=BTC-USDC
TEST_SYMBOL_ID=0
TEST_ASSET_ID=0
SUBACCOUNT=0
```

The node and Relayer URLs also accept the TypeScript example names
`FULLNODE_URL` and `DEX_REST_URL`. Replace the example URLs and market or asset
IDs with those for your network. Fund the trading account with the network's
USDC funding flow in addition to any native-coin faucet funding.

Run each entry from the repository root with `python dex-examples/<file>.py`.

| File | What it runs |
| --- | --- |
| `account_client_usage.py` | Pass `create`, `transfer --to-sub-address <address>`, `configure`, `adjust-margin`, or `authorize`. Transfer moves 10.5 USDC between existing subaccounts. Margin adjustment needs an open isolated long and sufficient available margin. |
| `18_unified_client_usage.py` | Pass `trade` for a BTC-USDC limit order or `account` to create a subaccount. After funding the subaccount during test setup, run `account --sub-address <address>` to set its leverage. |
| `e2e_order_lifecycle.py` | Place a bracket and a standalone limit, modify and cancel by client order ID, then close a net position. Use a local market with prices near the example's BTC-USDC levels, an open position, and available liquidity for the close. |
| `03_standard_transfer.py` | Create a subaccount and demonstrate internal and inter-account transfers. Set `RECIPIENT_PRIVATE_KEY` to a second test key. |
| `04_dex_place_order.py` | Place limit, market, and bracket orders. Pass `--hedge` with a funded account already in hedge mode to exercise long and short order placement. |
| `05_dex_cancel_order.py` | Place and cancel a test order. Set `ORDER_ID` to cancel an existing order on the selected subaccount. |
| `06_dex_replace_order.py` | Modify a test order by client order ID. Set `ORDER_ID` and `MODIFY_PRICE` to modify an existing order. |
| `07_dex_batch_orders.py` | Batch placement, modification, and cancellation. Set `SIZE` to a human-unit market size when needed. |
| `08_dex_user_config.py` | Change leverage, position mode, and margin mode on a flat test account. |
| `09_dex_transfer.py` | Create two subaccounts and move USDC between them. Set `BRIDGE_DESTINATION` to exercise withdrawal on a configured test bridge. `BRIDGE_WITHDRAW_AMOUNT` defaults to 10 USDC. |
| `11_dex_agent_wallet.py` | Approve a test agent, place and cancel a delegated order, then revoke the approval. Set `AGENT_PRIVATE_KEY` for a funded test agent or configure its faucet. |
| `e2e_intention_test.py` | Pass `--lane preflight` or `--lane minimal` for network checks and `--lane enhanced` for a confirmed market order. |

When running the account client or unified client subaccount creation again on
the same account, pass a fresh `--name`.

Run the SDK's deterministic tests with
`python -m unittest discover -t . -s tests -p 'test_*.py'`.
