#!/usr/bin/env python3
import asyncio
import argparse
import bbbot.join

parser = argparse.ArgumentParser(description="Generate an BBB join link for a Greenlight 2 room")
parser.add_argument("room", help="Greenlight 2 room URL, e.g. https://gl2.example.com/b/aaa-bbb-ccc-ddd")
parser.add_argument("name", help="Bot name", default="BOT")
parser.add_argument("--modkey", help="Moderator key")
args = parser.parse_args()

async def main():
    print(await bbbot.join.joinlink_from_greenlight2(
        args.room, args.name, modcode=args.modkey
    ))

asyncio.run(main())
