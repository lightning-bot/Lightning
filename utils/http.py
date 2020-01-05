# Lightning.py - A multi-purpose Discord bot
# Copyright (C) 2020 - LightSage
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation at version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


async def haste(session, text, instance='https://mystb.in/'):
    """Posts to a haste instance and returns the link.

    Parameters:
    ------------
    session: `aiohttp.ClientSession`

    text: str
        The text to post to the instance.

    instance: str
        Link to a haste instance. By default https://mystb.in/ is used."""
    response = await session.post(f"{instance}documents",
                                  data=text)
    if response.status == 200:
        result_json = await response.json()
        return f"{instance}{result_json['key']}"
    else:
        return f"Error {response.status}. Try again later?"


async def get(session, url):
    """Returns the text of a url

    If failed to get data, returns `False`
    Parameters:
    -------------
    session: `aiohttp.ClientSession`

    url: `str`
        A website url.
    """
    try:
        data = await session.get(url)
        if data.status == 200:
            text_data = await data.text()
            return text_data
        else:
            print(f"HTTP Error {data.status} "
                  f"while getting {url}")
            return False
    except Exception as e:
        print(f"Error while getting {url} "
              f"on get: {e}")
        return False


async def getbytes(session, url):
    """Returns the data of a url

    If failed to get data, returns `False`
    Parameters:
    -------------
    session: `aiohttp.ClientSession`

    url: `str`
        A website url"""
    try:
        data = await session.get(url)
        if data.status == 200:
            byte_data = await data.read()
            return byte_data
        else:
            print(f"HTTP Error {data.status} "
                  f"while getting {url}")
            return False
    except Exception as e:
        print(f"Error while getting {url} "
              f"on getbytes: {e}")
        return False


async def getjson(session, url):
    """Returns json from a url

    If failed to get data, returns `False`
    Parameters:
    -------------
    session: `aiohttp.ClientSession`

    url: `str`
        A website url"""
    try:
        data = await session.get(url)
        if data.status == 200:
            content_type = data.headers['Content-Type']
            return await data.json(content_type=content_type)
        else:
            print(f"HTTP Error {data.status} "
                  f"while getting {url}")
            return False
    except Exception as e:
        print(f"Error while getting {url} "
              f"on aiogetbytes: {e}")
        return False
