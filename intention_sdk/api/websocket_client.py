# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Relayer WebSocket subscriptions with reconnect and resubscribe support."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from ..core.account_address import AccountAddress

MessageHandler = Callable[[Any, Dict[str, Any]], Union[None, Awaitable[None]]]
ErrorHandler = Callable[[Exception], Union[None, Awaitable[None]]]
WebSocketFactory = Callable[[str], Awaitable[Any]]


async def _default_factory(url: str) -> Any:
    from websockets.asyncio.client import connect

    return await connect(url)


async def _call(callback: Optional[Callable[..., Any]], *args: Any) -> None:
    if callback is None:
        return
    result = callback(*args)
    if inspect.isawaitable(result):
        await result


@dataclass
class _Subscription:
    channel: str
    id: Optional[str]
    batched: bool
    on_snapshot: Optional[MessageHandler]
    on_update: Optional[MessageHandler]
    on_error: Optional[ErrorHandler]


class IntentionWebSocketClient:
    def __init__(
        self,
        ws_url: str,
        *,
        websocket_factory: Optional[WebSocketFactory] = None,
        reconnect_delay_secs: float = 0.5,
        max_reconnect_delay_secs: float = 10,
    ):
        if not ws_url:
            raise ValueError("ws_url is required")
        self.ws_url = ws_url
        self.websocket_factory = websocket_factory or _default_factory
        self.reconnect_delay_secs = reconnect_delay_secs
        self.max_reconnect_delay_secs = max_reconnect_delay_secs
        self._subscriptions: Dict[str, _Subscription] = {}
        self._socket: Optional[Any] = None
        self._runner: Optional[asyncio.Task] = None
        self._stopped = True

    @staticmethod
    def _key(channel: str, id_value: Optional[str]) -> str:
        return f"{channel}\0{id_value or ''}"

    async def connect(self) -> None:
        if self._runner is not None and not self._runner.done():
            return
        self._stopped = False
        self._runner = asyncio.create_task(self._run())
        await asyncio.sleep(0)

    async def close(self) -> None:
        self._stopped = True
        socket = self._socket
        self._socket = None
        if socket is not None:
            await socket.close()
        task = self._runner
        self._runner = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def subscribe(
        self,
        channel: str,
        *,
        id: Optional[str] = None,
        batched: bool = True,
        on_snapshot: Optional[MessageHandler] = None,
        on_update: Optional[MessageHandler] = None,
        on_error: Optional[ErrorHandler] = None,
    ) -> Callable[[], Awaitable[None]]:
        key = self._key(channel, id)
        if key in self._subscriptions:
            raise ValueError(f"already subscribed to {channel}/{id or ''}")
        subscription = _Subscription(
            channel,
            id,
            batched,
            on_snapshot,
            on_update,
            on_error,
        )
        self._subscriptions[key] = subscription
        was_connected = self._socket is not None
        await self.connect()
        if was_connected and self._socket is not None:
            await self._send_subscribe(subscription)

        async def unsubscribe() -> None:
            removed = self._subscriptions.pop(key, None)
            if removed is not None and self._socket is not None:
                await self._socket.send(
                    json.dumps(
                        {
                            "type": "unsubscribe",
                            "channel": channel,
                            "id": id,
                        }
                    )
                )

        return unsubscribe

    async def subscribe_markets(self, **handlers: Any):
        return await self.subscribe("v1_markets", **handlers)

    async def subscribe_orderbook(self, symbol: str, **handlers: Any):
        return await self.subscribe("v1_orderbook", id=symbol, **handlers)

    async def subscribe_trades(self, symbol: str, **handlers: Any):
        return await self.subscribe("v1_trades", id=symbol, **handlers)

    async def subscribe_subaccount(
        self,
        address: Union[str, AccountAddress],
        *,
        sub_address: Optional[Union[str, AccountAddress]] = None,
        **handlers: Any,
    ):
        master = str(
            address
            if isinstance(address, AccountAddress)
            else AccountAddress.from_str_relaxed(address)
        )
        if sub_address is None:
            id_value = master
        else:
            sub = (
                sub_address
                if isinstance(sub_address, AccountAddress)
                else AccountAddress.from_str_relaxed(sub_address)
            )
            id_value = master if not any(sub.address) else f"{master}/{sub}"
        return await self.subscribe("v1_subaccounts", id=id_value, **handlers)

    async def _send_subscribe(self, subscription: _Subscription) -> None:
        assert self._socket is not None
        await self._socket.send(
            json.dumps(
                {
                    "type": "subscribe",
                    "channel": subscription.channel,
                    "id": subscription.id,
                    "batched": subscription.batched,
                }
            )
        )

    async def _run(self) -> None:
        delay = self.reconnect_delay_secs
        while not self._stopped:
            try:
                socket = await self.websocket_factory(self.ws_url)
                self._socket = socket
                for subscription in self._subscriptions.values():
                    await self._send_subscribe(subscription)
                delay = self.reconnect_delay_secs
                while not self._stopped:
                    raw = await socket.recv()
                    await self._handle(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._socket = None
                for subscription in self._subscriptions.values():
                    await _call(subscription.on_error, exc)
                if self._stopped:
                    return
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay_secs)
            finally:
                if self._socket is not None:
                    socket = self._socket
                    self._socket = None
                    await socket.close()

    async def _handle(self, raw: Any) -> None:
        if isinstance(raw, bytes):
            raw = raw.decode()
        message = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(message, dict):
            return
        subscription = self._subscriptions.get(
            self._key(message.get("channel", ""), message.get("id"))
        )
        if subscription is None:
            return
        message_type = message.get("type")
        if message_type == "error":
            await _call(
                subscription.on_error,
                RuntimeError(message.get("message", "WebSocket API error")),
            )
            return
        contents = message.get("contents")
        if message_type == "subscribed":
            await _call(subscription.on_snapshot, contents, message)
        elif message_type == "channel_data":
            await _call(subscription.on_update, contents, message)
        elif message_type == "channel_batch_data":
            values = contents if isinstance(contents, list) else [contents]
            for value in values:
                await _call(subscription.on_update, value, message)
