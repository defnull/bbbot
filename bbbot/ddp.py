import asyncio
import json
from urllib.parse import urljoin, urlsplit
import aiohttp
import logging

from .utils import AsyncCloseable, Waiter

logger = logging.getLogger(__name__)


class DDPClient(AsyncCloseable):
    def __init__(self, http: aiohttp.ClientSession, url: str):
        AsyncCloseable.__init__(self)
        self.http = http
        self.url = url
        self.method_futures = {}
        self.id = 1
        self.collections = {}

        self._handshake_done = asyncio.Event()

    async def connect(self):
        url = urlsplit(self.url)
        url = urljoin(f"wss://{url.hostname}/{url.path}/", "./websocket")

        self.sock = await self.http.ws_connect(url)
        logger.info("Websocket connected")
        self.on_close(self.sock.close)

        asyncio.create_task(self.__read_loop())

        logger.info("Starting DDP session...")
        await self.send("connect", version="1", support=["1"])
        await self._handshake_done.wait()

    async def __read_loop(self):
        async for msg in self.sock:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await self.on_msg(msg)

    async def send(self, msg, **args):
        args["msg"] = msg
        payload = json.dumps(args)
        logger.debug("DDP >>> " + payload)
        await self.sock.send_str(payload)

    async def call(self, method, *params):
        self.id += 1
        nextid = str(self.id)
        future = self.method_futures[nextid] = asyncio.Future()
        await self.send("method", id=nextid, method=method, params=params)
        return await future

    async def on_msg(self, msg):
        logger.debug("DDP <<< " + msg.data)
        data = json.loads(msg.data)

        if data["msg"] == "connected":
            self.ddp_session = data["session"]
            self._handshake_done.set()

        elif data["msg"] == "failed":
            logger.error("DDP handshake failed!")
            await self.close()

        elif data["msg"] == "ping":
            await self.send("pong")

        elif data["msg"] == "result":
            future = self.method_futures.pop(data["id"])
            if future:
                future.set_result(data.get("result", None))

        elif data["msg"] == "updated":
            # Signals that some method calls have finished manipulating collections.
            pass

        elif data["msg"] == "nosub":
            for col in self.collections.values():
                if col.id == data["id"]:
                    col._unsub(data.get("error"))
                    break
        elif data["msg"] == "added":
            self.collection(data["collection"])._added(data["id"], data.get("fields"))
        elif data["msg"] == "changed":
            self.collection(data["collection"])._changed(data["id"], data.get("fields"), data.get("cleared"))
        elif data["msg"] == "removed":
            self.collection(data["collection"])._removed(data["id"])
        elif data["msg"] == "addedBefore":
            self.collection(data["collection"])._added(data["id"], data.get("fields"), before=data.get("before"))
        elif data["msg"] == "movedBefore":
            self.collection(data["collection"])._moved(data["id"], data.get("before"))
        elif data["msg"] == "ready":
            pass

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = DDPCollection(name, self)
        return self.collections[name]

class DDPCollection:
    def __init__(self, name, ddp):
        self.ddp = ddp
        self.name = name
        self.data = {}
        self.callbacks = []
        self.id = str(id(self))
        self.subscribed = asyncio.Event()

    async def sub(self):
        await self.ddp.send("sub", id=self.id, name=self.name)

    async def unsub(self):
        await self.ddp.send("unsub", id=self.id)

    def _unsub(self, error):
        self.subscribed.clear()
        self.data.clear()

    def on_change(self, func):
        self.callbacks.append(func)

    async def _trigger_change(self, id, old, new):
        for cb in self.callbacks:
            await cb(id, old, new)

    async def _added(self, id, fields, before=None):
        self.subscribed.set()
        self.data[id] = fields
        await self._trigger_change(id, None, fields)

    async def _changed(self, id, fields, cleared):
        self.subscribed.set()
        old = dict(self.data[id])
        doc = self.data[id]
        doc.update(fields or {})
        for key in cleared or []:
            doc.pop(key)
        self.data[id] = doc
        await self._trigger_change(id, old, doc)

    async def _removed(self, id):
        self.subscribed.set()
        old = self.data.pop(id)
        if old:
            await self._trigger_change(id, old, None)

    async def _moved(self, id, before=None):
        self.subscribed.set()
        # Ordered collections not supported yet
