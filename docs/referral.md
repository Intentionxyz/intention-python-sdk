# Referral client

`IntentionClient.referrals` uses the configured relayer for queries and its signer
and executor for transactions. For queries alone, use `ReferralClient(relayer_url)`
and call `await client.close()` when finished.

## Queries

Base URLs may include or omit `/v1`. In these examples, `sdk` is an
`IntentionClient` and `master` is the account being queried.

```python
overview = await sdk.referrals.get_overview(master)
resolved = await sdk.referrals.resolve_code("ABC123")
config = await sdk.referrals.get_config()
reserved = await sdk.referrals.get_reserved_codes()
availability = await sdk.referrals.get_code_availability("ABC123")
invitees = await sdk.referrals.get_invitees(master, limit=50)
sources = await sdk.referrals.get_sources(master, limit=50)
claims = await sdk.referrals.get_claims(master, limit=50, page=1)
fills = await sdk.referrals.get_fills(master, limit=50)
```

Code resolution and availability queries normalize codes to uppercase. Use
`resolved["referrer"]` for account queries. Unknown codes return HTTP 404; an
unready index returns 503. HTTP errors propagate as httpx exceptions.

List cursors are opaque. Invitees and claims also accept a positive 1-based
`page`; do not combine it with a non-empty `cursor`. Invitees support `sort_by`
values `timeJoined`, `volumeSinceBound`, `feePaid` and `commissionAccrued`, with
`sort_order` set to `asc` or `desc`. Omitted sorting uses newest bindings first.

## User actions

Use a unique integer nonce for every transaction.

```python
await sdk.referrals.register_code("ABC123", register_nonce)
await sdk.referrals.bind_referrer("DEF456", bind_nonce)
result = await sdk.referrals.claim(claim_nonce)
```

ClaimAll claims the full available on-chain reward balance. Preflight reads the
active configuration and indexed overview to check that claims are enabled and
the balance meets the configured minimum. The chain validates the final balance
at execution, so indexing delays or concurrent claims can cause rejection. The
SDK does not retry automatically.

For an authorized agent, `claim(claim_nonce, on_behalf_of=master)` claims for that
master; the chain fixes the recipient. `build_claim(master, claim_nonce,
on_behalf_of=master)` returns a payload for separate signing. `build_register_code`,
`build_bind_referrer` and `build_set_config` also expose unsigned payloads.
`set_config(parameters, nonce, proof, options=None)` requires the appropriate
administrator and committee authorization and submits BCS to preserve the proof.

## Amounts and events

Display amounts are fixed-six-decimal USDC strings; `*Quantums` fields are exact
integer strings. `asOfBlockHeight` and `sourceSeqId` describe indexed coverage,
which can lag behind the node.

The unified DEX decoder handles registration, binding, configuration, reserved
codes, claims and per-fill fee supplements. Join `DexReferralFeeEvent` to its
fill by block height, symbol, fill ID and account identity. The original fill fee
already includes the discount. An account's `cumulativeReferralCommission` is
that trading subaccount's accrual; use the referral overview for the inviter's
claimable balance. Decoding supports the current per-account fee layout.
