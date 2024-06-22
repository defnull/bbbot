import urllib.parse
import aiohttp
from bs4 import BeautifulSoup, Tag
import re
from urllib.parse import urljoin


def soupify(html):
    return BeautifulSoup(html, features="html.parser")


async def joinlink_from_greenlight2(roomlink, name, modcode=None):
    roomId = roomlink.rsplit("/", 1)[-1]

    async with aiohttp.ClientSession() as http:
        async with http.get(roomlink) as response:
            soup = soupify(await response.text())

        if modcode:
            form = soup.find("form", action=f"/b/{roomId}/login")
            formdata = {
                field["name"]: field.get("value", "")
                for field in form.find_all("input")
                if field["name"]
            }
            formdata["room[access_code]"] = modcode
            async with http.post(urljoin(roomlink, form["action"]), data=formdata) as response:
                soup = soupify(await response.text())

        form = soup.find("form", action=f"/b/{roomId}")
        formdata = {
            field["name"]: field.get("value", "")
            for field in form.find_all("input")
            if field["name"]
        }
        formdata[f"/b/{roomId}[join_name]"] = name
        async with http.post(
            urljoin(roomlink, form["action"]), data=formdata, allow_redirects=False
        ) as response:
            return response.headers["Location"]
