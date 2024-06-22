import typing
import aiohttp
import asyncio
import aiortc
import aiortc.contrib.media

from .utils import AsyncCloseable

import json

import logging
logger = logging.getLogger(__name__)

class SFUClient(AsyncCloseable):
    sock: typing.Optional[aiohttp.ClientWebSocketResponse]

    def __init__(self, http: aiohttp.ClientSession, url: str):
        AsyncCloseable.__init__(self)
        self.http = http
        self.url = url
        self.sessions = []
        self.sock = None
        self.iceServers = []

    def add_ice_server(self, url, username=None, credential=None):
        self.iceServers.append(
            aiortc.RTCIceServer(
                url,
                username=username,
                credential=credential,
            )
        )

    async def _connect(self):
        logger.info("Connecting to SFU socket ...")
        self.sock = await self.http.ws_connect(self.url)
        self.on_close(self.sock.close)

        async def readloop():
            assert self.sock
            async for msg in self.sock:
                await self._on_msg(msg)

        async def pingloop():
            while True:
                await self.send("ping")
                await asyncio.sleep(10)

        self.on_close(asyncio.create_task(pingloop()).cancel)
        self.on_close(asyncio.create_task(readloop()).cancel)
        logger.info("SFU connected")


    async def new_session(self, type="audio", role="recv"):
        assert self.sock

        session = RTCSession(
            self, type, role, aiortc.RTCConfiguration(iceServers=self.iceServers)
        )
        self.on_close(session.close)

        self.sessions.append(session)
        session.id = len(self.sessions)

        return session

    async def send(self, id, **args):
        assert self.sock
        args["id"] = id
        logger.debug("SFU >>> " + json.dumps(args))
        await self.sock.send_str(json.dumps(args))

    async def _on_msg(self, msg):
        logger.debug("SFU <<< " + msg.data)
        msg = json.loads(msg.data)

        if msg["id"] == "pong":
            pass
        elif msg["id"] == "startResponse":
            assert msg["response"] == "accepted"
            # We have no way (yet) to check which session this answer belongs to
            # So we assume it's the latest.
            await self.sessions[-1]._on_start_response(msg)


class RTCSession(AsyncCloseable):

    def __init__(self, sfu: SFUClient, type, role, rtc_config: aiortc.RTCConfiguration):
        AsyncCloseable.__init__(self)
        self.sfu = sfu
        self.type = type
        self.role = role
        self.id = 0
        self.state = "new"
        self.peer = aiortc.RTCPeerConnection(rtc_config)
        self.on_close(self.peer.close)

        self.tracks = []

        self._connected_future = asyncio.Future()

    async def connect(self):
        self.state = "starting"
        await self.sfu.send(
            "start",
            type=self.type,
            role=self.role,
            clientSessionNumber=self.id,
            extension=None,
            transparentListenOnly=False,
        )

        try:
            await asyncio.wait_for(self._connected_future, timeout=30)
        except TimeoutError:
            await self.close()
            raise

    async def _on_start_response(self, msg):
        logger.info("SFU accepted connection request")

        assert msg["response"] == "accepted"
        assert msg["type"] == self.type

        self.state = "accepted"
        try:
            logger.info("Initializing new peer connection ...")

            # @self.peer.on("icecandidate")
            # async def on_icecandidate(candidate):
            #     logger.debug(f"New ICE candidate: {candidate}")

            @self.peer.on("track")
            async def on_track(track):
                logger.debug(f"New track: {track.kind}")
                self.tracks.append(track)

            @self.peer.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                assert self.peer
                logger.debug(f"ICE connection state: {self.peer.iceConnectionState}")

            @self.peer.on("connectionstatechange")
            async def on_connectionstatechange():
                assert self.peer
                logger.debug(f"RTC Connection state: {self.peer.connectionState}")
                if self.peer.connectionState == "failed":
                    self._connected_future.set_exception(
                        IOError("RTC connection failed")
                    )
                    await self.close()
                elif self.peer.connectionState == "connected":
                    self._connected_future.set_result(self)

            logger.debug("Setting RTC remote description ...")
            await self.peer.setRemoteDescription(
                aiortc.RTCSessionDescription(sdp=msg["sdpAnswer"], type="offer")
            )

            logger.debug("Generating RTC answer ...")
            answer = await self.peer.createAnswer()
            assert answer

            logger.debug("Setting RTC local description ...")
            await self.peer.setLocalDescription(answer)
            sdpOffer = self.peer.localDescription.sdp

            logger.debug("Finishing SFU handshake ...")
            await self.sfu.send(
                "subscriberAnswer",
                type=self.type,
                role=self.role,
                sdpOffer=sdpOffer,
            )

        except Exception as e:
            self.state = "failed"
            if not self._connected_future.done():
                self._connected_future.set_exception(e)
            raise
