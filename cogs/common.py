# Whole Imported Cog from robocop-ng. with the removal of some things that won't be used.
# MIT License
# 
# Copyright (c) 2018 Arda "Ave" Ozkal
#
#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

import asyncio
import traceback
import datetime
import humanize
import time
import math
import parsedatetime
import subprocess
from discord.ext.commands import Cog

class Common(Cog):
    def __init__(self, bot):
        self.bot = bot

        self.bot.slice_message = self.slice_message
        self.max_split_length = 3
        self.bot.hex_to_int = self.hex_to_int
        self.bot.download_file = self.download_file
        self.bot.aiojson = self.aiojson
        self.bot.aioget = self.aioget
        self.bot.aiogetbytes = self.aiogetbytes
        self.bot.get_relative_timestamp = self.get_relative_timestamp
        self.bot.escape_message = self.escape_message
        self.bot.parse_time = self.parse_time
        self.bot.haste = self.haste
        self.bot.call_shell = self.call_shell
        self.bot.log.info(f'{self.qualified_name} loaded')


    def parse_time(self, delta_str):
        cal = parsedatetime.Calendar()
        time_struct, parse_status = cal.parse(delta_str)
        res_timestamp = math.floor(time.mktime(time_struct))
        return res_timestamp

    def get_relative_timestamp(self, time_from=None, time_to=None,
                               humanized=False, include_from=False,
                               include_to=False):
        # Setting default value to utcnow() makes it show time from cog load
        # which is not what we want
        if not time_from:
            time_from = datetime.datetime.utcnow()
        if not time_to:
            time_to = datetime.datetime.utcnow()
        if humanized:
            humanized_string = humanize.naturaltime(time_from - time_to)
            if include_from and include_to:
                str_with_from_and_to = f"{humanized_string} "\
                                       f"({str(time_from).split('.')[0]} "\
                                       f"- {str(time_to).split('.')[0]})"
                return str_with_from_and_to
            elif include_from:
                str_with_from = f"{humanized_string} "\
                                f"({str(time_from).split('.')[0]} UTC)"
                return str_with_from
            elif include_to:
                str_with_to = f"{humanized_string} "\
                              f"({str(time_to).split('.')[0]} UTC)"
                return str_with_to
            return humanized_string
        else:
            epoch = datetime.datetime.utcfromtimestamp(0)
            epoch_from = (time_from - epoch).total_seconds()
            epoch_to = (time_to - epoch).total_seconds()
            second_diff = epoch_to - epoch_from
            result_string = str(datetime.timedelta(
                seconds=second_diff)).split('.')[0]
            return result_string

    async def aioget(self, url):
        try:
            data = await self.bot.aiosession.get(url)
            if data.status == 200:
                text_data = await data.text()
                self.bot.log.info(f"Data from {url}: {text_data}")
                return text_data
            else:
                self.bot.log.error(f"HTTP Error {data.status} "
                                   "while getting {url}")
        except:
            self.bot.log.error(f"Error while getting {url} "
                               f"on aiogetbytes: {traceback.format_exc()}")

    async def aiogetbytes(self, url):
        try:
            data = await self.bot.aiosession.get(url)
            if data.status == 200:
                byte_data = await data.read()
                self.bot.log.debug(f"Data from {url}: {byte_data}")
                return f"Data from {url}:\n{byte_data}"
            else:
                self.bot.log.error(f"HTTP Error {data.status} "
                                   "while getting {url}")
        except:
            self.bot.log.error(f"Error while getting {url} "
                               f"on aiogetbytes: {traceback.format_exc()}")

    async def aiojson(self, url):
        try:
            data = await self.bot.aiosession.get(url)
            if data.status == 200:
                text_data = await data.text()
                self.bot.log.info(f"Data from {url}: {text_data}")
                content_type = data.headers['Content-Type']
                return await data.json(content_type=content_type)
            else:
                self.bot.log.error(f"HTTP Error {data.status} "
                                   "while getting {url}")
        except:
            self.bot.log.error(f"Error while getting {url} "
                               f"on aiogetbytes: {traceback.format_exc()}")

    def hex_to_int(self, color_hex: str):
        """Turns a given hex color into an integer"""
        return int("0x" + color_hex.strip('#'), 16)

    def escape_message(self, text: str):
        """Escapes unfun stuff from messages"""
        return str(text).replace("@", "@ ").replace("<#", "# ")

    # This function is based on https://stackoverflow.com/a/35435419/3286892
    # by link2110 (https://stackoverflow.com/users/5890923/link2110)
    # modified by Ave (https://github.com/aveao), licensed CC-BY-SA 3.0
    async def download_file(self, url, local_filename):
        file_resp = await self.bot.aiosession.get(url)
        file = await file_resp.read()
        with open(local_filename, "wb") as f:
            f.write(file)

    # 2000 is maximum limit of discord
    async def slice_message(self, text, size=2000, prefix="", suffix=""):
        """Slices a message into multiple messages"""
        if len(text) > size * self.max_split_length:
            haste_url = await self.haste(text)
            return [f"Message is too long ({len(text)} > "
                    f"{size * self.max_split_length} "
                    f"({size} * {self.max_split_length}))"
                    f", go to haste: <{haste_url}>"]
        reply_list = []
        size_wo_fix = size - len(prefix) - len(suffix)
        while len(text) > size_wo_fix:
            reply_list.append(f"{prefix}{text[:size_wo_fix]}{suffix}")
            text = text[size_wo_fix:]
        reply_list.append(f"{prefix}{text}{suffix}")
        return reply_list

    async def haste(self, text, instance='https://mystb.in/'):
        response = await self.bot.aiosession.post(f"{instance}documents",
                                                  data=text)
        if response.status == 200:
            result_json = await response.json()
            return f"{instance}{result_json['key']}"
        else:
            return f"Error {response.status}: {response.text}"

    # The function (call_shell) listed below is my work (LightSage). 
    # LICENSE: GNU Affero General Public License v3.0 
    # https://github.com/LightSage/Lightning.py/blob/master/LICENSE
    async def call_shell(self, shell_command: str):
        try:
            pipe = asyncio.subprocess.PIPE
            process = await asyncio.create_subprocess_shell(shell_command,
                                                            stdout=pipe,
                                                            stderr=pipe)
            stdout, stderr = await process.communicate()
        except NotImplementedError: # Account for Windows (Trashdows)
            process = subprocess.Popen(shell_command, shell=True, 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            
        msg1 = f"[stderr]\n{stderr.decode('utf-8')}\n---\n"\
               f"[stdout]\n{stdout.decode('utf-8')}"
               
        return msg1

def setup(bot):
    bot.add_cog(Common(bot))