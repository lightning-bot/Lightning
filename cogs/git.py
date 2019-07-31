from discord.ext import commands
import discord
import github3
import config
from utils.bot_mgmt import check_if_botmgmt
import datetime
import gitlab
from utils.checks import is_git_whitelisted

class Git(commands.Cog):
    """Helper Commands for GitHub/GitLab Related Things."""
    def __init__(self, bot):
        self.bot = bot
        self.gh = github3.login(token=config.github_key)
        self.gl = gitlab.Gitlab(config.gitlab_instance, private_token=config.gitlab_token)

    @commands.guild_only()
    @commands.check(check_if_botmgmt)
    @commands.group(aliases=['gh'])
    @commands.check(is_git_whitelisted)
    async def github(self, ctx):
        """Commands to help with GitHub"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.check(check_if_botmgmt)
    @commands.check(is_git_whitelisted)
    @github.command(aliases=['issuecomment', 'ic'])
    async def commentonissue(self, ctx, issue_number: int, *, comment: str):
        """Adds a comment to an issue"""
        try:
            issue = self.gh.issue(config.github_username, 
                                  config.github_repo, issue_number)
            if issue.is_closed():
                return await ctx.send(f"That issue is closed! (Since `{issue.closed_at}`)")
            issue.create_comment(f"**<{ctx.author}>**: {comment}")
            await ctx.send(f"Done! See {issue.html_url}")
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")

    @commands.check(check_if_botmgmt)
    @github.command()
    @commands.check(is_git_whitelisted)
    async def issuestatus(self, ctx, issue_number: int, status: str):
        """Changes the state of an issue. 
        
        Either pass 'open' or 'closed'
        """
        try:
            issue = self.gh.issue(config.github_username, 
                                  config.github_repo, issue_number)
            issue.edit(state=status)
            await ctx.send(f"Done! See {issue.html_url}")
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")

    @commands.check(check_if_botmgmt)
    @github.command()
    @commands.check(is_git_whitelisted)
    async def closeandcomment(self, ctx, issue_number: int, *, comment: str):
        """Comments then closes an issue"""
        try:
            issue = self.gh.issue(config.github_username, 
                                  config.github_repo, issue_number)
            if issue.is_closed():
                return await ctx.send(f"That issue is already closed! (Since `{issue.closed_at}`)")
            issue.create_comment(f"**<{ctx.author}>**: {comment}")
            issue.close()
            await ctx.send(f"Done! See {issue.html_url}")
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")

    @commands.check(check_if_botmgmt)
    @github.command()
    @commands.check(is_git_whitelisted)
    async def stats(self, ctx, number: int):
        """Prints an embed with various info on an issue or pull"""
        tmp = await ctx.send("Fetching info....")
        try:
            issue = self.gh.issue(config.github_username, 
                                  config.github_repo, number)
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

    @commands.check(check_if_botmgmt)
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

    @commands.check(check_if_botmgmt)
    @github.command()
    @commands.check(is_git_whitelisted)
    async def archivepins(self, ctx):
        """Creates a gist with the channel's pins
        
        Uses the channel that the command was invoked in."""
        pins = await ctx.channel.pins()
        if pins: # Does this channel have pins?
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

        files = {
            f'{ctx.channel.name} | {datetime.datetime.utcnow()}.md' : {
                'content': content_to_upload
                }
            }
        # Login with our token and create a gist
        gist = self.gh.create_gist(f'Pin Archive for {ctx.channel.name}.', 
                                   files, public=False)
        # Send the created gist's URL
        await ctx.send(f"You can find an archive of this channel's pins at {gist.html_url}")

        #for pm in pins: # Unpin our pins(?)
        #    await pm.unpin()

    @commands.check(check_if_botmgmt)
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
                        log_t += f"[{attach.filename}]({attach.url})\n\n" # hackyish
                else:
                    log_t += "\n\n"

        files = {
            f'{ctx.channel.name} | {datetime.datetime.utcnow()}.md' : {
                'content': log_t
                }
            }

        # Login with our token and create a gist
        gist = self.gh.create_gist(f'Message Archive for {ctx.channel.name}.', 
                                   files, public=False)
        # Send the created gist's URL
        await ctx.send(f"You can find an archive of this channel's history at {gist.html_url}")

    @commands.group(aliases=['gl'])
    @commands.check(check_if_botmgmt)
    @commands.check(is_git_whitelisted)
    async def gitlab(self, ctx):
        """Commands that help with GitLab things"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @gitlab.command()
    @commands.check(check_if_botmgmt)
    @commands.check(is_git_whitelisted)
    async def close(self, ctx, number: int):
        """Closes an issue"""
        project1 = self.gl.projects.get(config.gitlab_project_id, lazy=True)
        project = project1.issues.get(number, lazy=True)
        closev = project.state_event = 'close'
        if closev is not False:
            return await ctx.send("That Issue is Already Closed!")
        project.state_event = 'close'
        project.save()
        await ctx.send(f"Successfully closed {number}")

    @gitlab.command(aliases=['pc'])
    @commands.check(check_if_botmgmt)
    @commands.check(is_git_whitelisted)
    async def pipelinecancel(self, ctx, pipeline_number: int):
        """Cancels a pipeline by ID"""
        # We pass lazy so we don't make multiple calls
        try:
            project = self.gl.projects.get(config.gitlab_project_id, lazy=True)
            pipeline = project.pipelines.get(pipeline_number, lazy=True)
            pipeline.cancel()
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")
        await ctx.send(f"Successfully cancelled pipeline {pipeline_number}")

    @gitlab.command()
    @commands.check(check_if_botmgmt)
    @commands.check(is_git_whitelisted)
    async def listpipelines(self, ctx):
        """Lists all the pipelines for the repository"""
        try:
            project = self.gl.projects.get(config.gitlab_project_id, lazy=True)
            pipelines = project.pipelines.list()
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")
        paginator = commands.Paginator(prefix="", suffix="")
        paginator.add_line("🔧 __Pipelines:__")
        count = 0
        for pipe in pipelines:
            paginator.add_line(f"- #{pipe.id} (URL: <{pipe.web_url}>)")
            count += 1

        for page in paginator.pages:
            await ctx.send(page)

    @gitlab.command(aliases=['lp'])
    @commands.check(check_if_botmgmt)
    @commands.check(is_git_whitelisted)
    async def latestpipeline(self, ctx):
        """Grabs the most recent pipeline's ID and URL"""
        try:
            project = self.gl.projects.get(config.gitlab_project_id, lazy=True)
            pipe = project.pipelines.list()[0]
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")
        embed = discord.Embed(title=f"Pipeline Stats for #{pipe.id}", 
                              color=discord.Color.blue())
        embed.add_field(name="Branch", value=pipe.ref)
        embed.add_field(name="Status", value=pipe.status)
        embed.description = f"URL: {pipe.web_url}"
        await ctx.send(embed=embed)

    @gitlab.command(aliases=['mrc'])
    @commands.check(check_if_botmgmt)
    @commands.check(is_git_whitelisted)
    async def mrchange(self, ctx, mr_id: int, event: str):
        """Closes or Reopens a MR. Pass either `close` or `reopen` """
        try:
            project = self.gl.projects.get(config.gitlab_project_id, lazy=True)
            mr = project.mergerequests.get(mr_id)
            mr.state_event = event
            mr.save()
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")
        await ctx.send(f"Successfully changed !{mr_id}. {mr.web_url}")

    @gitlab.command(aliases=['lc'])
    @commands.check(check_if_botmgmt)
    @commands.check(is_git_whitelisted)
    async def labelcreate(self, ctx, label_name: str, color: str):
        """Creates a label"""
        try:
            project = self.gl.projects.get(config.gitlab_project_id, lazy=True)
            l = project.labels.create({'name': label_name, 'color': color})
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")
        await ctx.send(f"Succesfully created {l.name} (Color: {l.color})")

    @gitlab.command()
    async def merge(self, ctx, mr_id: int):
        """Merges a Merge Request"""
        try:
            project = self.gl.projects.get(config.gitlab_project_id, lazy=True)
            mr = project.mergerequests.get(mr_id)
            mr.merge()
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")
        await ctx.send(f"Successfully merged !{mr.iid} to {mr.target_branch}. {mr.web_url}")

def setup(bot):
    bot.add_cog(Git(bot))