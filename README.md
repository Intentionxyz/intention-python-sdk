# Intention Python SDK

Async Python SDK for Intention DEX accounts, trading, signing, event decoding
and real-time subscriptions. Requires Python 3.9 or later.

## Installation

```bash
git clone https://github.com/Intentionxyz/intention-python-sdk.git
cd intention-python-sdk
python -m pip install .
```

WebSocket support is included in the default installation.

## Quick start

```python
import asyncio
from intention_sdk import Intention, IntentionConfig, Network

async def main():
    sdk = Intention(IntentionConfig(
        network=Network.CUSTOM,
        node_url="http://127.0.0.1:8080/v1",
    ))
    info = await sdk.get_ledger_info()
    print(info["chain_id"])

asyncio.run(main())
```

Use your network's node URL. For signed trading, configure an `IntentionClient`
with a funded signer and the node and relayer URLs.

- [Integration guide](docs/simplified-integration-guide.md)
- [Referral client](docs/referral.md)
- [Vault event decoding](docs/vault-events-v1.md)
- [Examples](dex-examples/README.md)
- [TypeScript SDK](https://github.com/Intentionxyz/intention-ts-sdk)
