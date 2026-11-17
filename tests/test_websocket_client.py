# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import unittest

from intention_sdk.api.websocket_client import IntentionWebSocketClient


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.messages = asyncio.Queue()
        self.closed = False

    async def send(self, value):
        self.sent.append(json.loads(value))

    async def recv(self):
        return await self.messages.get()

    async def close(self):
        self.closed = True


class TestWebSocketClient(unittest.IsolatedAsyncioTestCase):
    async def test_default_transport_subscribes_and_receives_a_snapshot(self):
        from websockets.asyncio.server import serve

        received = asyncio.get_running_loop().create_future()
        subscribed = []

        async def relayer(socket):
            request = json.loads(await socket.recv())
            subscribed.append(request)
            await socket.send(
                json.dumps(
                    {
                        "type": "subscribed",
                        "channel": request["channel"],
                        "id": request["id"],
                        "contents": {"bids": []},
                    }
                )
            )
            await socket.wait_closed()

        async with serve(relayer, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            client = IntentionWebSocketClient(f"ws://127.0.0.1:{port}/ws")
            try:
                await client.subscribe_orderbook(
                    "BTC-USDC",
                    on_snapshot=lambda contents, _message: received.set_result(contents),
                )
                self.assertEqual(await asyncio.wait_for(received, 5), {"bids": []})
                self.assertEqual(
                    subscribed,
                    [{"type": "subscribe", "channel": "v1_orderbook",
                      "id": "BTC-USDC", "batched": True}],
                )
            finally:
                await client.close()

    async def test_subscription_routes_messages_and_unsubscribes(self):
        socket = FakeSocket()

        async def factory(_url):
            return socket

        snapshots = []
        updates = []
        client = IntentionWebSocketClient(
            "ws://localhost/ws", websocket_factory=factory
        )
        unsubscribe = await client.subscribe_orderbook(
            "BTC-USDC",
            on_snapshot=lambda contents, _message: snapshots.append(contents),
            on_update=lambda contents, _message: updates.append(contents),
        )
        await asyncio.sleep(0.01)
        self.assertEqual(socket.sent[0]["type"], "subscribe")
        await socket.messages.put(
            json.dumps(
                {
                    "type": "subscribed",
                    "channel": "v1_orderbook",
                    "id": "BTC-USDC",
                    "contents": {"bids": []},
                }
            )
        )
        await socket.messages.put(
            json.dumps(
                {
                    "type": "channel_batch_data",
                    "channel": "v1_orderbook",
                    "id": "BTC-USDC",
                    "contents": [{"price": "1"}, {"price": "2"}],
                }
            )
        )
        await asyncio.sleep(0.01)
        self.assertEqual(snapshots, [{"bids": []}])
        self.assertEqual(updates, [{"price": "1"}, {"price": "2"}])
        await unsubscribe()
        self.assertEqual(socket.sent[-1]["type"], "unsubscribe")
        await client.close()


if __name__ == "__main__":
    unittest.main()
