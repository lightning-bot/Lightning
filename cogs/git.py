# Lightning.py - A multi-purpose Discord bot
# Copyright (C) 2019 - LightSage
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

import datetime

import dateutil.parser
import discord
import github3
from discord.ext import commands

from utils.checks import is_bot_manager, is_git_whitelisted
from utils.errors import LightningError


class Git(commands.Cog):
    """Helper Commands for GitHub/GitLab Related Things."""
    def __init__(self, bot):
        self.bot = bot
        self.gh = github3.login(token=self.bot.config['git']['github']['key'])
        self.base_api_url = f"{self.bot.config['git']['gitlab']['instance']}/api/v4/projects"
        self.gitlab_headers = {"Private-Token": str(self.bot.config['git']['gitlab']['key']),
                               "User-Agent": "Lightning.py Git Cog"}

    async def cog_command_error(self, ctx, error):
        if isinstance(error, LightningError):
            return await ctx.send(f'```{error}```')
        elif isinstance(error, commands.CommandInvokeError):
            original = error.original
            if isinstance(original, discord.HTTPException):
                return await ctx.send(f"```HTTP Exception: {original}```")

    def create_api_url(self, path="/merge_requests",
                       project_id=None):
        if project_id is None:
            project_id = self.bot.config['git']['gitlab']['project_id']
        url = f"{self.base_api_url}/{project_id}{path}"
        return url

    def status_emoji(self, status: str):
        if status == "success":
            return "\U00002705"
        elif status == "failed":
            return "\U0000274c"
        elif status in ("running", "pending"):
            return "\U0000231b"
        # Unknown
        return "\U00002754"

    async def make_gitlab_request(self, method, url):
        """Makes a request to the Gitlab API

        Parameters
        -----------
        method: str
            The type of method to use.

        url: str
            The URL you are requesting.
        """
        async with self.bot.aiosession.request(method, url, headers=self.gitlab_headers) as resp:
            ratelimit = resp.headers.get("RateLimit-Remaining")
            if ratelimit == 0:
                raise LightningError("Ratelimited")
            if resp.status != 200:
                raise discord.HTTPException(response=resp, message=str(resp.reason))
            else:
                data = await resp.json()
        return data

    @commands.guild_only()
    @commands.check(is_bot_manager)
    @commands.group(aliases=['gh'])
    @commands.check(is_git_whitelisted)
    async def github(self, ctx):
        """Commands to help with GitHub"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    @github.command(aliases=['issuecomment', 'ic'])
    async def commentonissue(self, ctx, issue_number: int, *, comment: str):
        """Adds a comment to an issue"""
        try:
            issue = self.gh.issue(self.bot.config['git']['github']['username'],
                                  self.bot.config['git']['github']['repository_name'],
                                  issue_number)
            if issue.is_closed():
                return await ctx.send(f"That issue is closed! (Since `{issue.closed_at}`)")
            issue.create_comment(f"**<{ctx.author}>**: {comment}")
            await ctx.send(f"Done! See {issue.html_url}")
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")

    @commands.check(is_bot_manager)
    @github.command()
    @commands.check(is_git_whitelisted)
    async def issuestatus(self, ctx, issue_number: int, status: str):
        """Changes the state of an issue.

        Either pass 'open' or 'closed'
        """
        try:
            issue = self.gh.issue(self.bot.config['git']['github']['username'],
                                  self.bot.config['git']['github']['repository_name'],
                                  issue_number)
            issue.edit(state=status)
            await ctx.send(f"Done! See {issue.html_url}")
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")

    @commands.check(is_bot_manager)
    @github.command()
    @commands.check(is_git_whitelisted)
    async def closeandcomment(self, ctx, issue_number: int, *, comment: str):
        """Comments then closes an issue"""
        try:
            issue = self.gh.issue(self.bot.config['git']['github']['username'],
                                  self.bot.config['git']['github']['repository_name'],
                                  issue_number)
            if issue.is_closed():
                return await ctx.send(f"That issue is already closed! (Since `{issue.closed_at}`)")
            issue.create_comment(f"**<{ctx.author}>**: {comment}")
            issue.close()
            await ctx.send(f"Done! See {issue.html_url}")
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")

    @commands.check(is_bot_manager)
    @github.command()
    @commands.check(is_git_whitelisted)
    async def stats(self, ctx, number: int):
        """Prints an embed with various info on an issue or pull"""
        tmp = await ctx.send("Fetching info....")
        try:
            issue = self.gh.issue(self.bot.config['git']['github']['username'],
                                  self.bot.config['git']['github']['repository_name'],
                                  number)
        except Exception as e:
            return await tmp.edit(content=f"An Error Occurred! `{e}`")
        embed = discord.Embed(title=f"{issue.title} | #{issue.number}")
        if issue.is_closed():
            embed.color = discord.Color(0xFF0000)
            embed.add_field(name="Closed at", value=issue.closed_at)
        else:
            embed.color = discord.Color.green()
        embed.add_field(name="State", value=issue.state)
        embed.add_field(name="Opened by", value=issue.user)
        embed.add_field(name="Comment Count", value=issue.comments_count)
        embed.set_footer(text=f"BTW, {issue.ratelimit_remaining}")
        await tmp.edit(content=f"Here you go! <{issue.html_url}>")
        await ctx.send(embed=embed)

    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    @github.command(aliases=['rls'])
    async def ratelimitstats(self, ctx):
        """Sends an embed with some rate limit stats"""
        tmp = await ctx.send("Fetching ratelimit info...")
        rl = self.gh.rate_limit()
        embed = discord.Embed(title="Ratelimit Info")
        embed.add_field(name="Core", value=rl['resources']['core'])
        embed.add_field(name="Search", value=rl['resources']['search'])
        await tmp.delete()
        await ctx.send(embed=embed)

    @commands.check(is_bot_manager)
    @github.command()
    @commands.check(is_git_whitelisted)
    async def archivepins(self, ctx):
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
            return await ctx.send("Couldn\'t find any pins in this channel!"
                                  " Try another channel?")

        files = {f'{ctx.channel.name} | {datetime.datetime.utcnow()}.md': {
                 'content': content_to_upload}}
        # Login with our token and create a gist
        gist = self.gh.create_gist(f'Pin Archive for {ctx.channel.name}.',
                                   files, public=False)
        # Send the created gist's URL
        await ctx.send(f"You can find an archive of this channel's pins at {gist.html_url}")

        # for pm in pins: # Unpin our pins(?)
        #    await pm.unpin()

    @commands.check(is_bot_manager)
    @commands.command()
    @commands.check(is_git_whitelisted)
    async def archivegist(self, ctx, limit: int):
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

        files = {f'{ctx.channel.name} | {datetime.datetime.utcnow()}.md': {
                 'content': log_t}}

        # Login with our token and create a gist
        gist = self.gh.create_gist(f'Message Archive for {ctx.channel.name}.',
                                   files, public=False)
        # Send the created gist's URL
        await ctx.send(f"You can find an archive of this channel's history at {gist.html_url}")

    @commands.group(aliases=['gl'])
    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    async def gitlab(self, ctx):
        """Commands that help with GitLab things"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @gitlab.command(name="mergerequest", aliases=['mr'])
    @commands.check(is_git_whitelisted)
    async def get_merge_request(self, ctx, id: int):
        """Gives information for a merge request"""
        url = self.create_api_url() + f"/{id}"
        data = await self.make_gitlab_request("GET", url)
        em = discord.Embed(title=f"{data['title']} | !{id}")
        timestamp = dateutil.parser.isoparse(data['created_at'])
        em.set_footer(text="Created at")
        em.timestamp = timestamp
        em.set_author(name=data['author']['name'],
                      url=data['author']['web_url'],
                      icon_url=data['author']['avatar_url'])
        em.description = f"[{data['web_url']}]({data['web_url']})"
        pipeline = f"__URL__: [{data['pipeline']['web_url']}]({data['pipeline']['web_url']})"\
                   f"\n**Status**: {self.status_emoji(data['head_pipeline']['status'])}"
        em.add_field(name="**Pipeline Info**", value=pipeline)
        em.add_field(name="**Labels**",
                     value="> " + "\n> ".join(data['labels']), inline=False)
        if len(data['assignees']) != 0:
            assigned = []
            for e in data['assignees']:
                assigned.append(f"[{e['name']}]({e['web_url']})")
            em.add_field(name="**Assignees**", value="\n".join(assigned), inline=False)
        await ctx.send(embed=em)

    @gitlab.command()
    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    async def close(self, ctx, issue: int):
        """Closes an issue"""
        url = self.create_api_url(path=f"/issues/{issue}?state_event=close")
        await self.make_gitlab_request("PUT", url)
        await ctx.send(f"Successfully closed {issue}")

    @gitlab.command()
    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    async def listpipelines(self, ctx):
        """Lists all the pipelines for the repository"""
        url = self.create_api_url(path="/pipelines")
        data = await self.make_gitlab_request("GET", url)
        paginator = commands.Paginator(prefix="", suffix="")
        paginator.add_line("🔧 __Pipelines:__")
        count = 0
        for p in data:
            paginator.add_line(f"- #{p['id']} (URL: <{p['web_url']}>)")
            count += 1

        for page in paginator.pages:
            await ctx.send(page)

    @gitlab.command(aliases=['lp'])
    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    async def latestpipeline(self, ctx):
        """Grabs the most recent pipeline's ID and URL"""
        url = self.create_api_url(path="/pipelines")
        data = await self.make_gitlab_request("GET", url)
        data = data[0]
        embed = discord.Embed(title=f"Pipeline Stats for #{data['id']}",
                              color=discord.Color.blue())
        embed.add_field(name="Branch", value=data['ref'])
        embed.add_field(name="Status",
                        value=f"{self.status_emoji(data['status'])}"
                              f" {data['status'].title()}")
        embed.description = (f"URL: {data['web_url']}")
        await ctx.send(embed=embed)

    @gitlab.command(aliases=['mrc'])
    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    async def mrchange(self, ctx, mr_id: int, event: str):
        """Closes or Reopens a MR. Pass either `close` or `reopen` """
        url = self.create_api_url() + f"/{mr_id}?state_event={event}"
        data = await self.make_gitlab_request("PUT", url)
        await ctx.send(f"Successfully changed !{mr_id}. {data['web_url']}")

    @gitlab.command()
    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    async def merge(self, ctx, mr_id: int):
        """Merges a Merge Request"""
        url = self.create_api_url() + f"/{mr_id}/merge"
        data = await self.make_gitlab_request("PUT", url)
        await ctx.send(f"Successfully merged !{mr_id} to "
                       f"`{data['target_branch']}`. {data['web_url']}")

    @gitlab.command()
    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    async def addmrlabel(self, ctx, mr_id: int, *labels):
        """Adds a label to a merge request.

        Provide no labels to remove all labels"""
        url = self.create_api_url() + f"/{mr_id}"
        data = await self.make_gitlab_request("GET", url)
        _labels = [e for e in data['labels']]
        _labels.extend(labels)
        url = self.create_api_url() + f"/{mr_id}?labels={','.join(_labels)}"
        await self.make_gitlab_request("PUT", url)
        await ctx.send("Successfully added labels")

    @gitlab.command()
    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    async def addlabel(self, ctx, issue: int, *labels):
        """Adds a label to an issue.

        Provide no labels to remove all labels"""
        url = self.create_api_url(path=f"/issues/{issue}")
        data = await self.make_gitlab_request("GET", url)
        _labels = [e for e in data['labels']]
        _labels.extend(labels)
        url = self.create_api_url() + f"/{issue}?labels={','.join(_labels)}"
        await self.make_gitlab_request("PUT", url)
        await ctx.send("Successfully added labels")

    @gitlab.command(aliases=['listmrs'])
    @commands.check(is_bot_manager)
    @commands.check(is_git_whitelisted)
    async def openmrs(self, ctx):
        """Lists currently opened merge requests"""
        url = self.create_api_url(path="/merge_requests?state=opened")
        prs = await self.make_gitlab_request("GET", url)
        if len(prs) != 0:
            msgd = {}
            for p in prs:
                msgd[str(p['iid'])] = p['web_url']
            await ctx.send(f"Currently open merge requests: ```json\n{msgd}```")
        else:
            await ctx.send("No open merge requests!")


def setup(bot):
    bot.add_cog(Git(bot))
