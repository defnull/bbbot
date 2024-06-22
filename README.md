# Experimental BigBlueButton Bot

WORK IN PROGRESS

A lightweight and fast bot for BigBlueButton based on `aiohttp` and `aiortc`.

## How to run examples:

```shell
# Create and activate a fresh virtual environment
python3 -mvenv venv
. venv/bin/activate

# Install this module and its dependencies (dev build)
pip install -e .

# Patch aiortc if https://github.com/aiortc/aiortc/pull/1123 is not merged yet

# Join a running meeting using a valid join link:
./example/bot.py -vv https://bbb.example.com/api/bigbluebutton/join?[...]

# Oh join a Greenlight 2 room (no API secret needed):
./example/bot.py -vv $(./example/gl2join.py https://gl2.example.com/b/aaa-bbb-ccc-ddd TESTBOT --modkey abcdef)
```