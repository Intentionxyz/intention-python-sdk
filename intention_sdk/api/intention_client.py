# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unified user-facing SDK facade."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..core.account import Account
from ..core.account_address import AccountAddress, ParseAddressError
from ..transactions.account_client import AccountClient
from .client import ClientConfig, RestClient
from .dex_account_client import DexAccountClient, DexDelistingView
from .referral_client import ReferralClient
from .dex_executor import DexTransactionExecutor, SubmitOptions
from ..types.enums import OrderPositionMode
from .intention import Intention, IntentionConfig, Network
from ..transactions.market_resolver import MarketsClient
from .order_client import OrderClient
from ..transactions.order_intents import (
    MarketResolver,
    ModifyChanges,
    ModifyConditionChanges,
    OrderGroup,
    OrderInput,
    OrderRef,
    OrderType,
    TpSlLeg,
)
from .websocket_client import IntentionWebSocketClient, WebSocketFactory


def _address(value: Any) -> AccountAddress:
    if isinstance(value, AccountAddress):
        return value
    text = str(value)
    try:
        return AccountAddress.from_str(text)
    except (ParseAddressError, ValueError):
        return AccountAddress.from_str_relaxed(text)


class AccountsClient(AccountClient):
    """Account actions and node-backed account/order reads in one namespace."""

    def __init__(self, *args: Any, query: DexAccountClient, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.query = query

    async def get_accounts(self, address: Optional[Any] = None):
        return await self.query.get_accounts(address or self.signer.account_address)

    async def get_account(self, sub_address: Any, address: Optional[Any] = None):
        return await self.query.get_account(
            address or self.signer.account_address, sub_address
        )

    async def get_positions(self, sub_address: Any, address: Optional[Any] = None):
        return await self.query.get_positions(
            address or self.signer.account_address, sub_address
        )

    async def get_balances(self, sub_address: Any, address: Optional[Any] = None):
        return await self.query.get_balances(
            address or self.signer.account_address, sub_address
        )

    async def get_order(self, order_id: int):
        return await self.query.get_order(order_id)


class TraderClient:
    """Subaccount-scoped trading facade with lazy market/account preparation."""

    def __init__(
        self,
        sdk: "IntentionClient",
        *,
        sub_address: Any,
        address: Optional[Any] = None,
        position_mode: Optional[OrderPositionMode] = None,
        resolver: Optional[MarketResolver] = None,
    ):
        self.sdk = sdk
        self.sub_address = _address(sub_address)
        self.address = _address(address or sdk.signer.account_address)
        self._position_mode = position_mode
        self._resolver = resolver
        self._orders: Optional[OrderClient] = None

    async def _get_position_mode(self) -> OrderPositionMode:
        if self._position_mode is not None:
            return self._position_mode
        snapshot = await self.sdk.accounts.get_account(self.sub_address, self.address)
        if snapshot is None:
            raise ValueError(
                f"DEX subaccount {self.sub_address} was not found for {self.address}"
            )
        self._position_mode = OrderPositionMode(int(snapshot["position_mode"]))
        return self._position_mode

    async def _get_order_client(self) -> OrderClient:
        if self._orders is None:
            resolver = self._resolver or await self.sdk.markets.get_resolver()
            self._orders = OrderClient(
                executor=self.sdk.executor,
                signer=self.sdk.signer,
                sub_address=self.sub_address,
                position_mode=await self._get_position_mode(),
                resolver=resolver,
                node_url=self.sdk.config.node_url,
                relayer_url=self.sdk.config.relayer_url,
                headers=self.sdk.headers,
                trust_env=self.sdk.rest_client.client_config.trust_env,
                submit_options=self.sdk.submit_options,
                account_provider=self.sdk.accounts.query,
            )
        return self._orders

    async def prepare(self) -> "TraderClient":
        await self._get_order_client()
        return self

    def refresh(self) -> None:
        self._orders = None

    async def place_order(self, order: OrderInput, **options: Any):
        return await (await self._get_order_client()).place_order(order, **options)

    async def place_orders(self, groups: Sequence[OrderGroup], **options: Any):
        return await (await self._get_order_client()).place_orders(groups, **options)

    async def place_order_with_tpsl(
        self,
        entry: OrderInput,
        *,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
        **options: Any,
    ):
        return await (await self._get_order_client()).place_order_with_tpsl(
            entry, tp=tp, sl=sl, **options
        )

    async def place_position_tpsl(self, **options: Any):
        return await (await self._get_order_client()).place_position_tpsl(**options)

    async def place_order_with_tp_sl(
        self,
        entry: OrderInput,
        *,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
        **options: Any,
    ):
        return await self.place_order_with_tpsl(entry, tp=tp, sl=sl, **options)

    async def place_position_tp_sl(self, **options: Any):
        return await self.place_position_tpsl(**options)

    async def submit_order(self, order: OrderInput, **options: Any):
        return await (await self._get_order_client()).submit_order(order, **options)

    async def submit_orders(self, groups: Sequence[OrderGroup], **options: Any):
        return await (await self._get_order_client()).submit_orders(groups, **options)

    async def submit_order_with_tpsl(
        self,
        entry: OrderInput,
        *,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
        **options: Any,
    ):
        return await (await self._get_order_client()).submit_order_with_tpsl(
            entry, tp=tp, sl=sl, **options
        )

    async def submit_position_tpsl(self, **options: Any):
        return await (await self._get_order_client()).submit_position_tpsl(**options)

    async def submit_order_with_tp_sl(
        self,
        entry: OrderInput,
        *,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
        **options: Any,
    ):
        return await self.submit_order_with_tpsl(entry, tp=tp, sl=sl, **options)

    async def submit_position_tp_sl(self, **options: Any):
        return await self.submit_position_tpsl(**options)

    async def cancel_order(self, ref: OrderRef, **options: Any):
        return await (await self._get_order_client()).cancel_order(ref, **options)

    async def cancel_orders(self, refs: Sequence[OrderRef], **options: Any):
        return await (await self._get_order_client()).cancel_orders(refs, **options)

    async def cancel_all(self, **options: Any):
        return await (await self._get_order_client()).cancel_all(**options)

    async def submit_cancel_order(self, ref: OrderRef):
        return await (await self._get_order_client()).submit_cancel_order(ref)

    async def submit_cancel_orders(self, refs: Sequence[OrderRef]):
        return await (await self._get_order_client()).submit_cancel_orders(refs)

    async def submit_cancel_all(self, **options: Any):
        return await (await self._get_order_client()).submit_cancel_all(**options)

    async def modify_order(self, ref: OrderRef, changes: ModifyChanges, **options: Any):
        return await (await self._get_order_client()).modify_order(
            ref, changes, **options
        )

    async def modify_orders(
        self,
        changes: Sequence[Tuple[OrderRef, ModifyChanges]],
        **options: Any,
    ):
        return await (await self._get_order_client()).modify_orders(changes, **options)

    async def modify_condition_order(
        self,
        ref: OrderRef,
        changes: ModifyConditionChanges,
        **options: Any,
    ):
        return await (await self._get_order_client()).modify_condition_order(
            ref, changes, **options
        )

    async def modify_condition_orders(
        self,
        changes: Sequence[Tuple[OrderRef, ModifyConditionChanges]],
        **options: Any,
    ):
        return await (await self._get_order_client()).modify_condition_orders(
            changes, **options
        )

    async def submit_modify_order(self, ref: OrderRef, changes: ModifyChanges):
        return await (await self._get_order_client()).submit_modify_order(ref, changes)

    async def submit_modify_orders(
        self, changes: Sequence[Tuple[OrderRef, ModifyChanges]]
    ):
        return await (await self._get_order_client()).submit_modify_orders(changes)

    async def submit_modify_condition_order(
        self, ref: OrderRef, changes: ModifyConditionChanges
    ):
        return await (await self._get_order_client()).submit_modify_condition_order(
            ref, changes
        )

    async def submit_modify_condition_orders(
        self,
        changes: Sequence[Tuple[OrderRef, ModifyConditionChanges]],
    ):
        return await (await self._get_order_client()).submit_modify_condition_orders(
            changes
        )

    async def close_position(
        self,
        *,
        symbol: str,
        position_side: Optional[str] = None,
        size: Any = "ALL",
        order_type: OrderType = OrderType.MARKET,
        price: Optional[Any] = None,
        **options: Any,
    ):
        return await (await self._get_order_client()).close_position(
            symbol=symbol,
            position_side=position_side,
            size=size,
            order_type=order_type,
            price=price,
            **options,
        )

    async def close_positions(
        self, positions: Sequence[Dict[str, Any]], **options: Any
    ):
        return await (await self._get_order_client()).close_positions(
            positions, **options
        )

    async def submit_close_position(self, **position: Any):
        return await (await self._get_order_client()).submit_close_position(**position)

    async def submit_close_positions(self, positions: Sequence[Dict[str, Any]]):
        return await (await self._get_order_client()).submit_close_positions(positions)

    async def get_account(self):
        return await self.sdk.accounts.get_account(self.sub_address, self.address)

    async def get_positions(self):
        return await self.sdk.accounts.get_positions(self.sub_address, self.address)

    async def get_balances(self):
        return await self.sdk.accounts.get_balances(self.sub_address, self.address)

    async def get_order(self, order_id: int):
        return await self.sdk.accounts.get_order(order_id)

    async def set_leverage(self, updates: Sequence[Dict[str, Any]], **options: Any):
        account = await self._account_client_with_resolver()
        return await account.set_leverage(self.sub_address, updates, **options)

    async def set_position_mode(self, mode: Any, **options: Any):
        result = await self.sdk.accounts.set_position_mode(
            self.sub_address, mode, **options
        )
        self._position_mode = None
        self.refresh()
        return result

    async def set_margin_mode(self, updates: Sequence[Dict[str, Any]], **options: Any):
        account = await self._account_client_with_resolver()
        return await account.set_margin_mode(self.sub_address, updates, **options)

    async def adjust_isolated_margin(self, **options: Any):
        account = await self._account_client_with_resolver()
        return await account.adjust_isolated_margin(self.sub_address, **options)

    async def _account_client_with_resolver(self) -> AccountClient:
        return AccountClient(
            executor=self.sdk.executor,
            signer=self.sdk.signer,
            node_url=self.sdk.config.node_url,
            resolver=self._resolver or await self.sdk.markets.get_resolver(),
            headers=self.sdk.headers,
            trust_env=self.sdk.rest_client.client_config.trust_env,
            submit_options=self.sdk.submit_options,
        )


class IntentionClient:
    """One signer and one URL config for all user-level SDK actions."""

    def __init__(
        self,
        *,
        signer: Account,
        node_url: Optional[str] = None,
        fullnode: Optional[str] = None,
        relayer_url: Optional[str] = None,
        ws_url: Optional[str] = None,
        faucet: Optional[str] = None,
        indexer: Optional[str] = None,
        network: Network = Network.CUSTOM,
        client_config: Optional[ClientConfig] = None,
        submit_options: Optional[SubmitOptions] = None,
        headers: Optional[Dict[str, str]] = None,
        websocket_factory: Optional[WebSocketFactory] = None,
    ):
        resolved_node_url = node_url or fullnode or ""
        if not resolved_node_url:
            raise ValueError("node_url is required")
        self.signer = signer
        self.headers = dict(headers or {})
        self.submit_options = submit_options
        self._websocket_factory = websocket_factory
        self._realtime: Optional[IntentionWebSocketClient] = None
        self.config = IntentionConfig(
            network=network,
            node_url=resolved_node_url,
            relayer_url=relayer_url,
            ws_url=ws_url,
            faucet=faucet,
            indexer=indexer,
            client_config={"HEADERS": self.headers},
        )
        self.intention = Intention(self.config)
        self.rest_client = RestClient(
            resolved_node_url, client_config or ClientConfig()
        )
        self.executor = DexTransactionExecutor(self.rest_client, signer)
        self.referrals = ReferralClient(
            relayer_url or "", executor=self.executor, signer=signer,
            headers=self.headers, trust_env=self.rest_client.client_config.trust_env,
        )
        self.markets = MarketsClient(
            relayer_url or "",
            headers=self.headers,
            trust_env=self.rest_client.client_config.trust_env,
        )
        query = DexAccountClient(
            resolved_node_url,
            headers=self.headers,
            trust_env=self.rest_client.client_config.trust_env,
        )
        self.accounts = AccountsClient(
            executor=self.executor,
            signer=signer,
            node_url=resolved_node_url,
            headers=self.headers,
            trust_env=self.rest_client.client_config.trust_env,
            submit_options=submit_options,
            query=query,
        )

    @property
    def realtime(self) -> IntentionWebSocketClient:
        if self._realtime is None:
            self._realtime = IntentionWebSocketClient(
                self.config.ws_url,
                websocket_factory=self._websocket_factory,
            )
        return self._realtime

    def trader(
        self,
        *,
        sub_address: Any,
        address: Optional[Any] = None,
        position_mode: Optional[OrderPositionMode] = None,
        resolver: Optional[MarketResolver] = None,
    ) -> TraderClient:
        return TraderClient(
            self,
            sub_address=sub_address,
            address=address,
            position_mode=position_mode,
            resolver=resolver,
        )

    async def get_ledger_info(self):
        return await self.rest_client.info()

    async def get_delistings(self) -> List[DexDelistingView]:
        return await self.accounts.query.get_delistings()

    async def get_delisting(self, perpetual_id: int) -> Optional[DexDelistingView]:
        return await self.accounts.query.get_delisting(perpetual_id)

    async def wait_for_transaction(self, txn_hash: str, **options: Any):
        return await self.executor.wait_for_transaction(txn_hash, **options)

    async def close(self) -> None:
        if self._realtime is not None:
            await self._realtime.close()
            self._realtime = None
        await self.referrals.close()
        await self.rest_client.close()
