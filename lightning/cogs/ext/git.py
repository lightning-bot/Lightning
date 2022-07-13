"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation at version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import datetime
import os

import discord
from discord.ext import commands

from lightning import (LightningBot, LightningCog, LightningContext, command,
                       group)
from lightning.errors import LightningError
from lightning.utils.checks import is_git_whitelisted
from lightning.utils.helpers import run_in_shell


class GithubGist:
    __slots__ = ("url", "forks_url", "commits_url", "id", "node_id", "html_url", "description", "public")

    def __init__(self, data: dict):
        self.url = data['url']
        self.forks_url = data['forks_url']
        self.commits_url = data['commits_url']
        self.id = data['id']
        self.node_id = data['node_id']
        self.html_url = data['html_url']
        self.description = data['description']
        self.public = data['public']

    def __repr__(self):
        return f"<GithubGist id={self.id}>"


class Git(LightningCog):
    """Helper commands for GitHub/GitLab related things."""

    def __init__(self, bot: LightningBot):
        self.bot = bot
        self.github_headers = {"Authorization": f"token {self.bot.config['git']['github']['key']}"}
        self.base_api_url = f"{self.bot.config['git']['gitlab']['instance']}/api/v4/projects"
        self.gitlab_headers = {"Private-Token": str(self.bot.config['git']['gitlab']['key'])}

    async def cog_command_error(self, ctx: LightningContext, error) -> None:
        if isinstance(error, LightningError):
            await ctx.send(f'```{error}```')
        elif isinstance(error, commands.CommandInvokeError):
            original = error.original
            if isinstance(original, discord.HTTPException):
                await ctx.send(f"```HTTP Exception: {original}```")

    def create_api_url(self, path="/merge_requests", project_id=None) -> str:
        if project_id is None:
            project_id = self.bot.config['git']['gitlab']['project_id']
        url = f"{self.base_api_url}/{project_id}{path}"
        return url

    def status_emoji(self, status: str) -> str:
        if status == "success":
            return "\U00002705"
        elif status == "failed":
            return "\U0000274c"
        elif status in ("running", "pending"):
            return "\U0000231b"
        # Unknown
        return "\U00002754"

    async def make_request(self, method: str, url: str, *, github=False, json=None):
        """Makes a request to either the GitLab API or Github API

        Parameters
        -----------
        method: str
            The type of method to use.
        url: str
            The URL you are requesting.
        """
        if github:
            headers = self.github_headers
            headers.update({'Accept': 'application/vnd.github.v3+json'})
        else:
            headers = self.gitlab_headers
        headers.update({"User-Agent": "Lightning Bot Git Cog"})
        async with self.bot.aiosession.request(method, url, headers=headers, json=json) as resp:
            ratelimit = resp.headers.get("RateLimit-Remaining")
            if ratelimit == 0:
                raise LightningError("Currently ratelimited. Try again later(?)")
            elif 300 > resp.status >= 200:
                data = await resp.json()
            else:
                raise discord.HTTPException(response=resp, message=str(resp.reason))
        return data

    @command()
    async def latestchanges(self, ctx: LightningContext) -> None:
        cmd = r'git log -10 --pretty="[{}](https://github.com/lightning-bot/Lightning/commit/%H) %s (%cr)"'
        if os.name == "posix":
            cmd = cmd.format(r'\`%h\`')
        else:
            cmd = cmd.format('`%h`')
        stdout, stderr = await run_in_shell(cmd)
        embed = discord.Embed(description=stdout)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @group(aliases=['gh'])
    @commands.check(is_git_whitelisted)
    async def github(self, ctx: LightningContext) -> None:
        """Commands to help with GitHub"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @github.command()
    @commands.check(is_git_whitelisted)
    async def archivepins(self, ctx: LightningContext) -> None:
        """Creates a gist with the channel's pins

        Uses the channel that the command was invoked in."""
        pins = await ctx.channel.pins()
        if pins:  # Does this channel have pins?
            async with ctx.typing():
                reversed_pins = reversed(pins)
                content_to_upload = f"Created on {datetime.datetime.utcnow()}\n---\n"
                for pin in reversed_pins:
                    content_to_upload += f"- {pin.author} [{pin.created_at}]: {pin.content}\n"
                    if pin.attachments:
                        for attach in pin.attachments:
                            # Assuming it's just pics
                            content_to_upload += f"![{attach.filename}]({attach.url})\n"
                    else:
                        content_to_upload += "\n"
        else:
            await ctx.send("Couldn\'t find any pins in this channel! Try another channel?")
            return

        data = {"files": {f'{ctx.channel.name} | {datetime.datetime.utcnow()}.md': {'content': content_to_upload}},
                "public": False,
                "description": f"Archived Pins from #{ctx.channel.name}"}
        resp = await self.make_request("POST", "https://api.github.com/gists", github=True, json=data)
        gist = GithubGist(resp)
        # Send the created gist's URL
        await ctx.send(f"You can find an archive of this channel's pins at {gist.html_url}")

        # for pin in pins: # Unpin our pins(?)
        #    await pin.unpin()

    @github.command()
    @commands.check(is_git_whitelisted)
    async def archivegist(self, ctx: LightningContext, limit: int) -> None:
        """Creates a gist with every message in channel"""
        log_t = f"Archive of {ctx.channel} (ID: {ctx.channel.id}) "\
                f"made on {datetime.datetime.utcnow()}\n\n"
        async with ctx.typing():
            async for log in ctx.channel.history(limit=limit):
                log_t += f"[{str(log.created_at)}]: {log.author} - {log.clean_content}"
                if log.attachments:
                    for attach in log.attachments:
                        log_t += f"[{attach.filename}]({attach.url})\n\n"  # hackyish
                else:
                    log_t += "\n\n"

        data = {"files": {f'{ctx.channel.name} | {datetime.datetime.utcnow()}.md': {'content': log_t}},
                "public": False,
                "description": f"Archived Messages from #{ctx.channel.name}"}

        # Login with our token and create a gist
        resp = await self.make_request("POST", "https://api.github.com/gists", github=True, json=data)
        gist = GithubGist(resp)
        # Send the created gist's URL
        await ctx.send(f"You can find an archive of this channel's history at {gist.html_url}")

    @group(aliases=['gl'])
    @commands.check(is_git_whitelisted)
    async def gitlab(self, ctx: LightningContext) -> None:
        """Commands that help with GitLab things"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @gitlab.command()
    @commands.check(is_git_whitelisted)
    async def close(self, ctx: LightningContext, issue: int, *, comment: str = '') -> None:
        """Closes an issue with an optional comment"""
        if comment:
            url = self.create_api_url(path=f"/issues/{issue}/notes?body={comment}")
            await self.make_request("POST", url)
        url = self.create_api_url(path=f"/issues/{issue}?state_event=close")
        await self.make_request("PUT", url)
        await ctx.send(f"Successfully closed {issue}")

    @gitlab.command()
    @commands.check(is_git_whitelisted)
    async def listpipelines(self, ctx: LightningContext) -> None:
        """Lists all the pipelines for the repository"""
        url = self.create_api_url(path="/pipelines")
        data = await self.make_request("GET", url)
        paginator = commands.Paginator(prefix="", suffix="")
        paginator.add_line("🔧 __Pipelines:__")
        count = 0
        for p in data:
            paginator.add_line(f"- #{p['id']} (URL: <{p['web_url']}>)")
            count += 1

        for page in paginator.pages:
            await ctx.send(page)

    @gitlab.command(aliases=['lp'])
    @commands.check(is_git_whitelisted)
    async def latestpipeline(self, ctx: LightningContext) -> None:
        """Grabs the most recent pipeline's ID and URL"""
        url = self.create_api_url(path="/pipelines")
        data = await self.make_request("GET", url)
        data = data[0]
        embed = discord.Embed(title=f"Pipeline Stats for #{data['id']}",
                              color=discord.Color.blue())
        embed.add_field(name="Branch", value=data['ref'])
        embed.add_field(name="Status",
                        value=f"{self.status_emoji(data['status'])}"
                              f" {data['status'].title()}")
        embed.description = (f"URL: {data['web_url']}")
        await ctx.send(embed=embed)

    @gitlab.command()
    @commands.check(is_git_whitelisted)
    async def addmrlabel(self, ctx: LightningContext, mr_id: int, *labels) -> None:
        """Adds a label to a merge request.

        Provide no labels to remove all labels"""
        url = self.create_api_url() + f"/{mr_id}"
        data = await self.make_request("GET", url)
        _labels = [e for e in data['labels']]
        _labels.extend(labels)
        url = self.create_api_url() + f"/{mr_id}?labels={','.join(_labels)}"
        await self.make_request("PUT", url)
        await ctx.send("Successfully added labels")

    @gitlab.command()
    @commands.check(is_git_whitelisted)
    async def addlabel(self, ctx: LightningContext, issue: int, *labels) -> None:
        """Adds a label to an issue.

        Provide no labels to remove all labels"""
        url = self.create_api_url(path=f"/issues/{issue}")
        data = await self.make_request("GET", url)
        _labels = [e for e in data['labels']]
        _labels.extend(labels)
        url = self.create_api_url(path=f"/issues/{issue}?labels={','.join(_labels)}")
        await self.make_request("PUT", url)
        await ctx.send("Successfully added labels")


async def setup(bot: LightningBot) -> None:
    await bot.add_cog(Git(bot))
