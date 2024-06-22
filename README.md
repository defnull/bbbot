# Experimental BigBlueButton

How to run examples:

* Install `poetry` and activate a virtual environment: `poetry shell`
* Install module and dependencies: `poetry install`
* Patch `aiortc` with https://github.com/aiortc/aiortc/pull/1123 if not already merged by upstream
* Fetch a join URL: `JOIN=$(poetry run examples/gl2join.py https://gl2.example.com/b/aaa-bbb-ccc-ddd TESTBOT --modkey abcdef)`
* Run the example bot: `poetry run example/bot.py -vv "$JOIN"`
* Watch an endless stream of log output and audio frames

