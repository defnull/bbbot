import typing
import urllib.parse
import aiohttp
import asyncio
import re
import urllib.parse
import aiortc
import aiortc.contrib.media

from urllib.parse import urljoin, parse_qs

from .ddp import DDPClient
from .utils import soupify, AsyncCloseable
from .rtc import SFUClient
import json

import logging
logger = logging.getLogger(__name__)


class StateError(RuntimeError):
    pass


class BBBClient(AsyncCloseable):
    http: aiohttp.ClientSession
    sfu: typing.Optional[SFUClient]

    def __init__(self):
        AsyncCloseable.__init__(self)
        self.http = aiohttp.ClientSession()
        self.on_close(self.http.close)
        self.sfu = None
        self._statelock = asyncio.Lock()

    async def join(self, joinlink):
        logger.info("Joining meeting ...")
        async with self.http.get(joinlink) as response:
            self.session_token = response.real_url.query["sessionToken"]
            html = soupify(await response.text())

        logger.info("Searching for Meteor config...")
        script = html.find("script", text=re.compile("__meteor_runtime_config__"))
        if not script:
            raise StateError("Failed to find meteor config <script>")
        mconf = script.text.split('"')[-2]
        mconf = json.loads(urllib.parse.unquote(mconf))
        self.meteor = mconf
        logger.debug(f"Meteor config: {self.meteor}")

        self.api_base = mconf["PUBLIC_SETTINGS"]["app"]["bbbWebBase"] + "/"

        logger.info("Connecting to DDP...")
        self.ddp = DDPClient(self.http, self.meteor["DDP_DEFAULT_CONNECTION_URL"])
        self.on_close(self.ddp.close)
        await self.ddp.connect()

        logger.info("Entering meeting ...")
        async with self.http.get(
            urljoin(self.api_base, "./api/enter"),
            params={"sessionToken": self.session_token},
        ) as response:
            self.meeting = (await response.json())["response"]
        logger.debug(f"Meeting metadata: {self.meeting}")

        # TODO: Wait for guest allow event?

        logger.info("Authenticating Session ...")
        await self.ddp.call(
            "validateAuthToken",
            self.meeting["meetingID"],
            self.meeting["internalUserID"],
            self.meeting["authToken"],
            self.meeting["externUserID"],
        )

    async def _initSFU(self):
        async with self._statelock:
            if not self.sfu:
                logger.info("Initializing SFU signaling ...")
                sfuURL = self.meteor["PUBLIC_SETTINGS"]["kurento"]["wsUrl"]
                sfuURL += f"?sessionToken={self.session_token}"
                sfu = SFUClient(self.http, sfuURL)

                logger.info("Fetching STUN/TURN info")
                stunFecthUrl = self.meteor["PUBLIC_SETTINGS"]["media"][
                    "stunTurnServersFetchAddress"
                ]
                async with self.http.get(
                    stunFecthUrl, params={"sessionToken": self.session_token}
                ) as response:
                    stunInfo = await response.json()
                    for stun in stunInfo.get("stunServers", []):
                        sfu.add_ice_server(stun["url"])
                    for turn in stunInfo.get("turnServers", []):
                        sfu.add_ice_server(
                            turn["url"], turn.get("username"), turn.get("password")
                        )

                await sfu._connect()
                self.sfu = sfu

        return self.sfu

    async def with_audio(self, listenonly=False):
        sfu = await self._initSFU()
        return await sfu.new_session(
            type="audio", role="recv" if listenonly else "sendrecv"
        )
    
    async def wait(self):
        await self.wait_closed()


