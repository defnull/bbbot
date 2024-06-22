#!/usr/bin/env python3
import asyncio
import argparse
import bbbot.client

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s]: %(message)s")

parser = argparse.ArgumentParser(description="Example BBB bot")
parser.add_argument("joinlink", help="BBB Join link")
parser.add_argument("--verbose", "-v", action="count", default=0)
args = parser.parse_args()

if args.verbose >= 1:
    logging.getLogger("bbbot").setLevel(logging.DEBUG)
if args.verbose >= 2:
    logging.getLogger("ROOT").setLevel(logging.DEBUG)

async def main():
    async with bbbot.client.BBBClient() as client:

        # Join this meeting
        await client.join(args.joinlink)

        # Prepare to connect via audio
        audio = await client.with_audio(listenonly=True)

        # Do stuff with audio frames
        async def read_loop(track):
            while True:
                pkg = await track.recv()
                print(pkg)

        # Wait for an audio track and start consuming it
        @audio.peer.on("track")
        async def on_track(track):
            # Do not sleep here, spawn a new coroutine
            asyncio.create_task(read_loop(track))

        # Actually (try to) connect to audio
        await audio.connect()

        # Sleep until meeting stops or client disconnects
        await client.wait()

asyncio.run(main())
