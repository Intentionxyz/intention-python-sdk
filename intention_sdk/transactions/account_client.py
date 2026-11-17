# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Pure account-action builders and their default-wait execution client."""

from __future__ import annotations

import math
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, Sequence, Union

import httpx

from ..core.account import Account
from ..core.account_address import AccountAddress, ParseAddressError

if TYPE_CHECKING:  # pragma: no cover
    # api.dex_executor reaches back here, and these four are only ever
    # annotations -- which `from __future__ import annotations` keeps lazy.
    from ..api.dex_executor import (
        DexExecutionResult,
        DexTransactionExecutor,
        PendingTransactionResult,
        SubmitOptions,
    )
from .dex_payloads import (
    AccountTransferItem,
    AdjustIsolatedMargin,
    AgentApprove,
    AgentRevoke,
    BridgeProof,
    ChangeMarginMode,
    ChangePositionMode,
    CreateSubAccount,
    CrossTransferItem,
    DexAgentTx,
    DexOrderlessTx,
    DexTransferTx,
    DexUserConfigTx,
    InternalTransferItem,
    ModifySubAccount,
    SetUserLeverage,
    SymbolMarginMode,
    UserSymbolLeverage,
)
from ..types.enums import (
    AccountType,
    AgentOperationVariant,
    CrossTransferOption,
    DexOrderlessTxVariant,
    DexTransferVariant,
    DexUserConfigTxVariant,
    MarginMode,
    OrderPositionMode,
)
from .order_intents import MarketResolver, NumberLike

AddressInput = Union[str, AccountAddress]
DEFAULT_AGENT_EXPIRY_SECONDS = 30 * 24 * 60 * 60


def _address(value: AddressInput) -> AccountAddress:
    if isinstance(value, AccountAddress):
        return value
    try:
        return AccountAddress.from_str(value)
    except (ParseAddressError, ValueError):
        return AccountAddress.from_str_relaxed(value)


def _nonce(value: Optional[int]) -> int:
    result = int(time.time() * 1_000_000) if value is None else int(value)
    if result < 0 or result > 2**64 - 1:
        raise ValueError("nonce must fit in u64")
    return result


def _name(value: str, field: str, max_bytes: int = 64) -> str:
    result = value.strip()
    if not result:
        raise ValueError(f"{field} cannot be empty")
    if len(result.encode("utf-8")) > max_bytes:
        raise ValueError(f"{field} cannot exceed {max_bytes} UTF-8 bytes")
    return result


def _amount(
    *,
    amount: Optional[NumberLike] = None,
    amount_atomic: Optional[int] = None,
    decimals: int = 6,
) -> int:
    if (amount is None) == (amount_atomic is None):
        raise ValueError("provide exactly one of amount or amount_atomic")
    if amount_atomic is not None:
        result = int(amount_atomic)
    else:
        try:
            decimal = Decimal(str(amount).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"invalid amount: {amount!r}") from exc
        if not decimal.is_finite():
            raise ValueError("amount must be finite")
        result = int(decimal.scaleb(decimals).to_integral_value(rounding=ROUND_DOWN))
    if result <= 0 or result > 2**64 - 1:
        raise ValueError("resolved atomic amount must be within u64 and positive")
    return result


def _position_mode(value: Union[str, OrderPositionMode]) -> OrderPositionMode:
    if value in ("one-way", "net", OrderPositionMode.NET):
        return OrderPositionMode.NET
    if value in ("hedge", OrderPositionMode.HEDGE):
        return OrderPositionMode.HEDGE
    raise ValueError("mode must be 'one-way' or 'hedge'")


def _leverage(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError("leverage must be a finite positive number")
    return result


def _margin_mode(value: Union[str, MarginMode]) -> MarginMode:
    mapping = {
        "cross": MarginMode.CROSS,
        "isolated": MarginMode.ISOLATED,
        "portfolio": MarginMode.PORTFOLIO,
    }
    if isinstance(value, str):
        try:
            return mapping[value.lower()]
        except KeyError as exc:
            raise ValueError(
                "mode must be 'cross', 'isolated', or 'portfolio'"
            ) from exc
    return MarginMode(value)


class AccountIntents:
    """Pure builders for wallet-adapter or custom-signing integrations."""

    def __init__(self, resolver: Optional[MarketResolver] = None):
        self.resolver = resolver

    def _symbol_id(self, *, symbol: Optional[str], symbol_id: Optional[int]) -> int:
        if (symbol is None) == (symbol_id is None):
            raise ValueError("provide exactly one of symbol or symbol_id")
        if symbol is not None:
            if self.resolver is None:
                raise ValueError("a market resolver is required when using symbol")
            return self.resolver.symbol_id(symbol)
        assert symbol_id is not None
        if symbol_id < 0 or symbol_id > 2**32 - 1:
            raise ValueError("symbol_id must fit in u32")
        return symbol_id

    @staticmethod
    def _user_config(variant: DexUserConfigTxVariant, payload: Any) -> DexOrderlessTx:
        return DexOrderlessTx(
            DexOrderlessTxVariant.DEX_USER_CONFIG,
            DexUserConfigTx(variant, payload),
        )

    def create_subaccount(
        self, name: str, *, nonce: Optional[int] = None
    ) -> DexOrderlessTx:
        return self._user_config(
            DexUserConfigTxVariant.CREATE_SUB_ACCOUNT,
            CreateSubAccount(_nonce(nonce), _name(name, "subaccount name", 16)),
        )

    def modify_subaccount(
        self,
        name: str,
        sub_address: AddressInput,
        *,
        on_behalf_of: Optional[AddressInput] = None,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        return self._user_config(
            DexUserConfigTxVariant.MODIFY_SUB_ACCOUNT,
            ModifySubAccount(
                _nonce(nonce),
                _name(name, "subaccount name", 16),
                _address(sub_address),
                _address(on_behalf_of) if on_behalf_of is not None else None,
            ),
        )

    def set_leverage(
        self,
        sub_address: AddressInput,
        updates: Sequence[Mapping[str, Any]],
        *,
        on_behalf_of: Optional[AddressInput] = None,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        if not updates:
            raise ValueError("updates cannot be empty")
        items = [
            UserSymbolLeverage(
                self._symbol_id(
                    symbol=update.get("symbol"),
                    symbol_id=update.get("symbol_id"),
                ),
                _leverage(update["leverage"]),
            )
            for update in updates
        ]
        ids = [item.symbol_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("updates cannot contain duplicate symbols")
        return self._user_config(
            DexUserConfigTxVariant.SET_USER_LEVERAGE,
            SetUserLeverage(
                _nonce(nonce),
                _address(sub_address),
                items,
                _address(on_behalf_of) if on_behalf_of is not None else None,
            ),
        )

    def set_position_mode(
        self,
        sub_address: AddressInput,
        mode: Union[str, OrderPositionMode],
        *,
        on_behalf_of: Optional[AddressInput] = None,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        return self._user_config(
            DexUserConfigTxVariant.CHANGE_POSITION_MODE,
            ChangePositionMode(
                _nonce(nonce),
                _address(sub_address),
                _position_mode(mode),
                _address(on_behalf_of) if on_behalf_of is not None else None,
            ),
        )

    def set_margin_mode(
        self,
        sub_address: AddressInput,
        updates: Sequence[Mapping[str, Any]],
        *,
        on_behalf_of: Optional[AddressInput] = None,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        if not updates:
            raise ValueError("updates cannot be empty")
        items = [
            SymbolMarginMode(
                self._symbol_id(
                    symbol=update.get("symbol"),
                    symbol_id=update.get("symbol_id"),
                ),
                _margin_mode(update["mode"]),
            )
            for update in updates
        ]
        ids = [item.symbol_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("updates cannot contain duplicate symbols")
        return self._user_config(
            DexUserConfigTxVariant.CHANGE_MARGIN_MODE,
            ChangeMarginMode(
                _nonce(nonce),
                _address(sub_address),
                items,
                _address(on_behalf_of) if on_behalf_of is not None else None,
            ),
        )

    def adjust_isolated_margin(
        self,
        sub_address: AddressInput,
        *,
        side: str,
        action: str,
        symbol: Optional[str] = None,
        symbol_id: Optional[int] = None,
        amount: Optional[NumberLike] = None,
        amount_atomic: Optional[int] = None,
        decimals: int = 6,
        on_behalf_of: Optional[AddressInput] = None,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        if side not in ("long", "short"):
            raise ValueError("side must be 'long' or 'short'")
        if action not in ("add", "remove"):
            raise ValueError("action must be 'add' or 'remove'")
        value = _amount(amount=amount, amount_atomic=amount_atomic, decimals=decimals)
        if value > 2**63 - 1:
            raise ValueError("isolated margin amount must fit in i64")
        delta = value if action == "add" else -value
        return self._user_config(
            DexUserConfigTxVariant.ADJUST_ISOLATED_MARGIN,
            AdjustIsolatedMargin(
                _nonce(nonce),
                _address(sub_address),
                self._symbol_id(symbol=symbol, symbol_id=symbol_id),
                delta if side == "long" else 0,
                delta if side == "short" else 0,
                _address(on_behalf_of) if on_behalf_of is not None else None,
            ),
        )

    def approve_agent(
        self,
        name: str,
        agent: Union[Account, AddressInput],
        *,
        expiry_timestamp: Optional[int] = None,
        expires_in_secs: int = DEFAULT_AGENT_EXPIRY_SECONDS,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        agent_address = (
            agent.account_address if isinstance(agent, Account) else _address(agent)
        )
        if not agent_address.is_evm_compatible():
            raise ValueError("agent address must be EVM compatible")
        now = int(time.time())
        if expiry_timestamp is None:
            if not 0 < expires_in_secs <= DEFAULT_AGENT_EXPIRY_SECONDS:
                raise ValueError(
                    f"expires_in_secs must be between 1 and "
                    f"{DEFAULT_AGENT_EXPIRY_SECONDS}"
                )
            expiry_timestamp = now + expires_in_secs
        if not now < expiry_timestamp <= now + DEFAULT_AGENT_EXPIRY_SECONDS:
            raise ValueError("agent expiry must be in the next 30 days")
        return DexOrderlessTx(
            DexOrderlessTxVariant.DEX_AGENT,
            DexAgentTx(
                _nonce(nonce),
                AgentOperationVariant.APPROVE,
                AgentApprove(
                    _name(name, "agent name", 20),
                    agent_address,
                    expiry_timestamp,
                ),
            ),
        )

    def revoke_agent(self, name: str, *, nonce: Optional[int] = None) -> DexOrderlessTx:
        return DexOrderlessTx(
            DexOrderlessTxVariant.DEX_AGENT,
            DexAgentTx(
                _nonce(nonce),
                AgentOperationVariant.REVOKE,
                AgentRevoke(_name(name, "agent name", 20)),
            ),
        )

    def transfer_between_subaccounts(
        self,
        from_sub_address: AddressInput,
        to_sub_address: AddressInput,
        *,
        amount: Optional[NumberLike] = None,
        amount_atomic: Optional[int] = None,
        decimals: int = 6,
        asset_id: int = 0,
        account_type: AccountType = AccountType.PERP,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        source = _address(from_sub_address)
        destination = _address(to_sub_address)
        if source == destination:
            raise ValueError("source and destination subaccounts must differ")
        return self.transfer_between_subaccounts_batch(
            [
                {
                    "from_sub_address": source,
                    "to_sub_address": destination,
                    "amount": amount,
                    "amount_atomic": amount_atomic,
                    "decimals": decimals,
                    "asset_id": asset_id,
                    "account_type": account_type,
                }
            ],
            nonce=nonce,
        )

    def transfer_between_subaccounts_batch(
        self,
        transfers: Sequence[Mapping[str, Any]],
        *,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        if not transfers:
            raise ValueError("transfers cannot be empty")
        items = []
        for transfer in transfers:
            source = _address(transfer["from_sub_address"])
            destination = _address(transfer["to_sub_address"])
            if source == destination:
                raise ValueError("source and destination subaccounts must differ")
            items.append(
                InternalTransferItem(
                    source,
                    destination,
                    int(transfer.get("asset_id", 0)),
                    _amount(
                        amount=transfer.get("amount"),
                        amount_atomic=transfer.get("amount_atomic"),
                        decimals=int(transfer.get("decimals", 6)),
                    ),
                    AccountType(transfer.get("account_type", AccountType.PERP)),
                )
            )
        return DexOrderlessTx(
            DexOrderlessTxVariant.DEX_TRANSFER,
            DexTransferTx(_nonce(nonce), DexTransferVariant.INTERNAL_TRANSFER, items),
        )

    def transfer_to_accounts(
        self,
        transfers: Sequence[Mapping[str, Any]],
        *,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        if not transfers:
            raise ValueError("transfers cannot be empty")
        items = [
            AccountTransferItem(
                _address(transfer["to_account"]),
                int(transfer.get("asset_id", 0)),
                _amount(
                    amount=transfer.get("amount"),
                    amount_atomic=transfer.get("amount_atomic"),
                    decimals=int(transfer.get("decimals", 6)),
                ),
                AccountType(transfer.get("account_type", AccountType.SPOT)),
            )
            for transfer in transfers
        ]
        return DexOrderlessTx(
            DexOrderlessTxVariant.DEX_TRANSFER,
            DexTransferTx(_nonce(nonce), DexTransferVariant.ACCOUNT_TRANSFER, items),
        )

    def bridge_withdraw(
        self,
        transfers: Sequence[Mapping[str, Any]],
        *,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        if not transfers:
            raise ValueError("transfers cannot be empty")
        items = []
        for transfer in transfers:
            destination = _address(transfer["destination"])
            if not destination.is_evm_compatible():
                raise ValueError("bridge withdrawal destination must be EVM compatible")
            items.append(
                CrossTransferItem(
                    destination,
                    int(transfer.get("asset_id", 0)),
                    _amount(
                        amount=transfer.get("amount"),
                        amount_atomic=transfer.get("amount_atomic"),
                        decimals=int(transfer.get("decimals", 6)),
                    ),
                    AccountType(transfer.get("account_type", AccountType.PERP)),
                )
            )
        return DexOrderlessTx(
            DexOrderlessTxVariant.DEX_TRANSFER,
            DexTransferTx(
                _nonce(nonce),
                DexTransferVariant.CROSS_TRANSFER,
                items,
                option=CrossTransferOption.BURN,
            ),
        )

    def bridge_deposit(
        self,
        transfers: Sequence[Mapping[str, Any]],
        proof: BridgeProof,
        *,
        nonce: Optional[int] = None,
    ) -> DexOrderlessTx:
        if not transfers:
            raise ValueError("transfers cannot be empty")
        if not proof.signatures:
            raise ValueError("bridge proof must contain at least one signature")
        items = [
            CrossTransferItem(
                _address(transfer["to_account"]),
                int(transfer.get("asset_id", 0)),
                _amount(
                    amount=transfer.get("amount"),
                    amount_atomic=transfer.get("amount_atomic"),
                    decimals=int(transfer.get("decimals", 6)),
                ),
                AccountType(transfer.get("account_type", AccountType.PERP)),
            )
            for transfer in transfers
        ]
        return DexOrderlessTx(
            DexOrderlessTxVariant.DEX_TRANSFER,
            DexTransferTx(
                _nonce(nonce),
                DexTransferVariant.CROSS_TRANSFER,
                items,
                option=CrossTransferOption.MINT,
                bridge_proof=proof,
            ),
        )


class AccountClient:
    def __init__(
        self,
        *,
        executor: DexTransactionExecutor,
        signer: Account,
        node_url: str,
        resolver: Optional[MarketResolver] = None,
        headers: Optional[Mapping[str, str]] = None,
        trust_env: bool = True,
        submit_options: Optional[SubmitOptions] = None,
    ):
        self.executor = executor
        self.signer = signer
        self.node_url = node_url.rstrip("/")
        self.headers = dict(headers or {})
        self.trust_env = trust_env
        self.submit_options = submit_options
        self.build = AccountIntents(resolver)

    def generate_agent_account(self) -> Account:
        return Account.generate()

    async def _execute(
        self,
        orderless: DexOrderlessTx,
        *,
        timeout_secs: float = 30,
        poll_interval_secs: float = 1,
    ) -> DexExecutionResult:
        return await self.executor.execute_orderless(
            orderless,
            options=self.submit_options,
            timeout_secs=timeout_secs,
            poll_interval_secs=poll_interval_secs,
        )

    async def _submit(self, orderless: DexOrderlessTx) -> PendingTransactionResult:
        return await self.executor.submit_orderless(
            orderless, options=self.submit_options
        )

    async def create_subaccount(self, name: str, **options: Any) -> DexExecutionResult:
        return await self._execute(
            self.build.create_subaccount(name, nonce=options.pop("nonce", None)),
            **options,
        )

    async def submit_create_subaccount(
        self, name: str, *, nonce: Optional[int] = None
    ) -> PendingTransactionResult:
        return await self._submit(self.build.create_subaccount(name, nonce=nonce))

    async def modify_subaccount(
        self, name: str, sub_address: AddressInput, **options: Any
    ) -> DexExecutionResult:
        return await self._execute(
            self.build.modify_subaccount(
                name,
                sub_address,
                on_behalf_of=options.pop("on_behalf_of", None),
                nonce=options.pop("nonce", None),
            ),
            **options,
        )

    async def submit_modify_subaccount(
        self,
        name: str,
        sub_address: AddressInput,
        *,
        on_behalf_of: Optional[AddressInput] = None,
        nonce: Optional[int] = None,
    ) -> PendingTransactionResult:
        return await self._submit(
            self.build.modify_subaccount(
                name,
                sub_address,
                on_behalf_of=on_behalf_of,
                nonce=nonce,
            )
        )

    async def set_leverage(
        self,
        sub_address: AddressInput,
        updates: Sequence[Mapping[str, Any]],
        **options: Any,
    ) -> DexExecutionResult:
        return await self._execute(
            self.build.set_leverage(
                sub_address,
                updates,
                on_behalf_of=options.pop("on_behalf_of", None),
                nonce=options.pop("nonce", None),
            ),
            **options,
        )

    async def submit_set_leverage(
        self,
        sub_address: AddressInput,
        updates: Sequence[Mapping[str, Any]],
        *,
        on_behalf_of: Optional[AddressInput] = None,
        nonce: Optional[int] = None,
    ) -> PendingTransactionResult:
        return await self._submit(
            self.build.set_leverage(
                sub_address,
                updates,
                on_behalf_of=on_behalf_of,
                nonce=nonce,
            )
        )

    async def set_position_mode(
        self,
        sub_address: AddressInput,
        mode: Union[str, OrderPositionMode],
        **options: Any,
    ) -> DexExecutionResult:
        return await self._execute(
            self.build.set_position_mode(
                sub_address,
                mode,
                on_behalf_of=options.pop("on_behalf_of", None),
                nonce=options.pop("nonce", None),
            ),
            **options,
        )

    async def submit_set_position_mode(
        self,
        sub_address: AddressInput,
        mode: Union[str, OrderPositionMode],
        *,
        on_behalf_of: Optional[AddressInput] = None,
        nonce: Optional[int] = None,
    ) -> PendingTransactionResult:
        return await self._submit(
            self.build.set_position_mode(
                sub_address,
                mode,
                on_behalf_of=on_behalf_of,
                nonce=nonce,
            )
        )

    async def set_margin_mode(
        self,
        sub_address: AddressInput,
        updates: Sequence[Mapping[str, Any]],
        **options: Any,
    ) -> DexExecutionResult:
        return await self._execute(
            self.build.set_margin_mode(
                sub_address,
                updates,
                on_behalf_of=options.pop("on_behalf_of", None),
                nonce=options.pop("nonce", None),
            ),
            **options,
        )

    async def submit_set_margin_mode(
        self,
        sub_address: AddressInput,
        updates: Sequence[Mapping[str, Any]],
        *,
        on_behalf_of: Optional[AddressInput] = None,
        nonce: Optional[int] = None,
    ) -> PendingTransactionResult:
        return await self._submit(
            self.build.set_margin_mode(
                sub_address,
                updates,
                on_behalf_of=on_behalf_of,
                nonce=nonce,
            )
        )

    async def adjust_isolated_margin(
        self, sub_address: AddressInput, **options: Any
    ) -> DexExecutionResult:
        timeout = options.pop("timeout_secs", 30)
        poll = options.pop("poll_interval_secs", 1)
        orderless = self.build.adjust_isolated_margin(sub_address, **options)
        return await self._execute(
            orderless, timeout_secs=timeout, poll_interval_secs=poll
        )

    async def submit_adjust_isolated_margin(
        self, sub_address: AddressInput, **options: Any
    ) -> PendingTransactionResult:
        return await self._submit(
            self.build.adjust_isolated_margin(sub_address, **options)
        )

    async def approve_agent(
        self, name: str, agent: Union[Account, AddressInput], **options: Any
    ) -> DexExecutionResult:
        if (
            agent.account_address if isinstance(agent, Account) else _address(agent)
        ) == self.signer.account_address:
            raise ValueError("cannot authorize signer as its own agent")
        timeout = options.pop("timeout_secs", 30)
        poll = options.pop("poll_interval_secs", 1)
        return await self._execute(
            self.build.approve_agent(name, agent, **options),
            timeout_secs=timeout,
            poll_interval_secs=poll,
        )

    async def submit_approve_agent(
        self, name: str, agent: Union[Account, AddressInput], **options: Any
    ) -> PendingTransactionResult:
        agent_address = (
            agent.account_address if isinstance(agent, Account) else _address(agent)
        )
        if agent_address == self.signer.account_address:
            raise ValueError("cannot authorize signer as its own agent")
        return await self._submit(self.build.approve_agent(name, agent, **options))

    async def revoke_agent(self, name: str, **options: Any) -> DexExecutionResult:
        return await self._execute(
            self.build.revoke_agent(name, nonce=options.pop("nonce", None)),
            **options,
        )

    async def submit_revoke_agent(
        self, name: str, *, nonce: Optional[int] = None
    ) -> PendingTransactionResult:
        return await self._submit(self.build.revoke_agent(name, nonce=nonce))

    async def transfer_between_subaccounts(
        self,
        from_sub_address: AddressInput,
        to_sub_address: AddressInput,
        **options: Any,
    ) -> DexExecutionResult:
        timeout = options.pop("timeout_secs", 30)
        poll = options.pop("poll_interval_secs", 1)
        return await self._execute(
            self.build.transfer_between_subaccounts(
                from_sub_address, to_sub_address, **options
            ),
            timeout_secs=timeout,
            poll_interval_secs=poll,
        )

    async def submit_transfer_between_subaccounts(
        self,
        from_sub_address: AddressInput,
        to_sub_address: AddressInput,
        **options: Any,
    ) -> PendingTransactionResult:
        return await self._submit(
            self.build.transfer_between_subaccounts(
                from_sub_address, to_sub_address, **options
            )
        )

    async def transfer_between_subaccounts_batch(
        self, transfers: Sequence[Mapping[str, Any]], **options: Any
    ) -> DexExecutionResult:
        timeout = options.pop("timeout_secs", 30)
        poll = options.pop("poll_interval_secs", 1)
        return await self._execute(
            self.build.transfer_between_subaccounts_batch(
                transfers, nonce=options.pop("nonce", None)
            ),
            timeout_secs=timeout,
            poll_interval_secs=poll,
        )

    async def submit_transfer_between_subaccounts_batch(
        self,
        transfers: Sequence[Mapping[str, Any]],
        *,
        nonce: Optional[int] = None,
    ) -> PendingTransactionResult:
        return await self._submit(
            self.build.transfer_between_subaccounts_batch(transfers, nonce=nonce)
        )

    async def deposit_to_subaccount(
        self, sub_address: AddressInput, **options: Any
    ) -> DexExecutionResult:
        return await self.transfer_between_subaccounts(
            self.signer.account_address, sub_address, **options
        )

    async def submit_deposit_to_subaccount(
        self, sub_address: AddressInput, **options: Any
    ) -> PendingTransactionResult:
        return await self.submit_transfer_between_subaccounts(
            self.signer.account_address, sub_address, **options
        )

    async def withdraw_to_main(
        self, sub_address: AddressInput, **options: Any
    ) -> DexExecutionResult:
        return await self.transfer_between_subaccounts(
            sub_address, self.signer.account_address, **options
        )

    async def submit_withdraw_to_main(
        self, sub_address: AddressInput, **options: Any
    ) -> PendingTransactionResult:
        return await self.submit_transfer_between_subaccounts(
            sub_address, self.signer.account_address, **options
        )

    async def transfer_to_account(
        self, to_account: AddressInput, **options: Any
    ) -> DexExecutionResult:
        if _address(to_account) == self.signer.account_address:
            raise ValueError("cannot transfer funds to signer account itself")
        timeout = options.pop("timeout_secs", 30)
        poll = options.pop("poll_interval_secs", 1)
        transfer = {"to_account": to_account, **options}
        nonce = transfer.pop("nonce", None)
        return await self._execute(
            self.build.transfer_to_accounts([transfer], nonce=nonce),
            timeout_secs=timeout,
            poll_interval_secs=poll,
        )

    async def submit_transfer_to_account(
        self, to_account: AddressInput, **options: Any
    ) -> PendingTransactionResult:
        if _address(to_account) == self.signer.account_address:
            raise ValueError("cannot transfer funds to signer account itself")
        transfer = {"to_account": to_account, **options}
        nonce = transfer.pop("nonce", None)
        return await self._submit(
            self.build.transfer_to_accounts([transfer], nonce=nonce)
        )

    async def transfer_to_accounts(
        self, transfers: Sequence[Mapping[str, Any]], **options: Any
    ) -> DexExecutionResult:
        if any(
            _address(transfer["to_account"]) == self.signer.account_address
            for transfer in transfers
        ):
            raise ValueError("cannot transfer funds to signer account itself")
        timeout = options.pop("timeout_secs", 30)
        poll = options.pop("poll_interval_secs", 1)
        return await self._execute(
            self.build.transfer_to_accounts(
                transfers, nonce=options.pop("nonce", None)
            ),
            timeout_secs=timeout,
            poll_interval_secs=poll,
        )

    async def submit_transfer_to_accounts(
        self,
        transfers: Sequence[Mapping[str, Any]],
        *,
        nonce: Optional[int] = None,
    ) -> PendingTransactionResult:
        if any(
            _address(transfer["to_account"]) == self.signer.account_address
            for transfer in transfers
        ):
            raise ValueError("cannot transfer funds to signer account itself")
        return await self._submit(
            self.build.transfer_to_accounts(transfers, nonce=nonce)
        )

    async def bridge_withdraw(
        self, transfers: Sequence[Mapping[str, Any]], **options: Any
    ) -> DexExecutionResult:
        timeout = options.pop("timeout_secs", 30)
        poll = options.pop("poll_interval_secs", 1)
        return await self._execute(
            self.build.bridge_withdraw(transfers, nonce=options.pop("nonce", None)),
            timeout_secs=timeout,
            poll_interval_secs=poll,
        )

    async def submit_bridge_withdraw(
        self,
        transfers: Sequence[Mapping[str, Any]],
        *,
        nonce: Optional[int] = None,
    ) -> PendingTransactionResult:
        return await self._submit(self.build.bridge_withdraw(transfers, nonce=nonce))

    async def bridge_deposit(
        self,
        transfers: Sequence[Mapping[str, Any]],
        proof: BridgeProof,
        **options: Any,
    ) -> DexExecutionResult:
        timeout = options.pop("timeout_secs", 30)
        poll = options.pop("poll_interval_secs", 1)
        return await self._execute(
            self.build.bridge_deposit(
                transfers, proof, nonce=options.pop("nonce", None)
            ),
            timeout_secs=timeout,
            poll_interval_secs=poll,
        )

    async def submit_bridge_deposit(
        self,
        transfers: Sequence[Mapping[str, Any]],
        proof: BridgeProof,
        *,
        nonce: Optional[int] = None,
    ) -> PendingTransactionResult:
        return await self._submit(
            self.build.bridge_deposit(transfers, proof, nonce=nonce)
        )

    async def get_agents(
        self, master_address: Optional[AddressInput] = None
    ) -> Dict[str, Any]:
        address = _address(master_address or self.signer.account_address)
        async with httpx.AsyncClient(trust_env=self.trust_env) as client:
            response = await client.get(
                f"{self.node_url}/dex/agents/{address}",
                headers={"Accept": "application/json", **self.headers},
            )
            response.raise_for_status()
            return response.json()

    async def get_agent_binding(
        self, agent_address: AddressInput
    ) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient(trust_env=self.trust_env) as client:
            response = await client.get(
                f"{self.node_url}/dex/agent_binding/{_address(agent_address)}",
                headers={"Accept": "application/json", **self.headers},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            body = response.json()
            return body if isinstance(body, dict) else None
