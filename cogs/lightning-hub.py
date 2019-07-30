from discord.ext import commands
import discord
import db.per_guild_config
import db.mod_check
from utils.restrictions import add_restriction, remove_restriction
import config
from utils.bot_mgmt import check_if_botmgmt
import github3
import datetime
from utils.checks import is_guild

class LightningHub(commands.Cog):
    """Helper commands for Lightning Hub only."""
    def __init__(self, bot):
        self.bot = bot
        self.gh = github3.login(token=config.github_key)
        self.bot.log.info(f'{self.qualified_name} loaded')

    # Snippet of Code taken from Noirscape's kirigiri. https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/LICENSE
    async def cog_before_invoke(self, ctx):
        if db.per_guild_config.exist_guild_config(ctx.guild, "config"):
            ctx.guild_config = db.per_guild_config.get_guild_config(ctx.guild, "config")
        else:
            ctx.guild_config = {}

    async def cog_after_invoke(self, ctx):
        db.per_guild_config.write_guild_config(ctx.guild, ctx.guild_config, "config")

    @commands.command()
    @is_guild(527887739178188830)
    @commands.has_any_role("Trusted", "Verified")
    async def sr(self, ctx, *, text: str = ""):
        """Request staff assistance. Trusted and Verified only."""
        staff = self.bot.get_channel(536376192727646208)
        if text:
            # Prevent extra mentions. We'll clean this later.
            embed = discord.Embed(color=discord.Color.red())
            embed.description = text
            embed.add_field(name="Jump!", value=f"{ctx.message.jump_url}")
        await staff.send(f"‼ {ctx.author.mention} needs a staff member. @here", embed=(embed if text != "" else None))
        await ctx.message.add_reaction("✅")
        await ctx.send("Online staff have been notified of your request.", delete_after=50)

    @commands.command()
    @is_guild(527887739178188830)
    @commands.has_any_role("Helpers", "Staff")
    async def probate(self, ctx, target: discord.Member, *, reason: str = ""):
        """Probates a user. Staff only."""
        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        role = discord.Object(id=546379342943617025)
        dm_message = f"You were probated on {ctx.guild.name}."
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."

        await target.add_roles(role, reason=str(ctx.author))
        msg = f"❗️ **Probate**: {ctx.author.mention} probated {target.mention} | {safe_name}"
        if reason:
            msg += f"✏️ __Reason__: \"{reason}\""
        else:
            msg += f"\nPlease add an explanation below. In the future" \
                    f", it is recommended to use " \
                    f"`{ctx.prefix}probate <user> [reason]`" \
                    f" as the reason is automatically sent to the user."
        try:
            await target.send(dm_message)
        except discord.errors.Forbidden:
            # Prevents issues in cases where user blocked bot
            # or has DMs disabled
            msg += f"\n\n{target.mention} has their DMs off and I was unable to send the reason."# Experimental
            pass

        add_restriction(ctx.guild, target.id, role.id)
        await mod_log_chan.send(msg)
        await ctx.send(f"{target.mention} is now probated.")

    @commands.command()
    @is_guild(527887739178188830)
    @commands.has_any_role("Helpers", "Staff")
    async def unprobate(self, ctx, target: discord.Member, *, reason: str = ""):
        """Removes probation role/unprobates the user. Staff only."""
        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        role = discord.Object(id=546379342943617025)
        
        await target.remove_roles(role, reason=str(ctx.author))
        msg = f"❗️ **Unprobate**: {ctx.author.mention} unprobated {target.mention} | {safe_name}"
        if reason:
            msg += f"✏️ __Reason__: \"{reason}\""
        else:
            msg += f"\nPlease add an explanation below. In the future" \
                    f", it is recommended to use " \
                    f"`{ctx.prefix}unprobate <user> [reason]`" 

        remove_restriction(ctx.guild, target.id, role.id)
        await mod_log_chan.send(msg)
        await ctx.send(f"{target.mention} is now unprobated.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.bot.wait_until_ready()
        if member.guild.id != 527887739178188830:
            return
        if db.per_guild_config.exist_guild_config(member.guild, "config"):
            config = db.per_guild_config.get_guild_config(member.guild, "config")
            if "auto_probate" in config:
                role = discord.Object(id=546379342943617025)
                await member.add_roles(role, reason="Auto Probate")
                dm_message = f"You were automatically probated. Please read the rules for this server and speak in the probation channel when you are ready."
                msg = f"**Auto Probate:** {member.mention}"
                try:
                    await member.send(dm_message)
                except discord.errors.Forbidden:
                    msg += "\nUnable to deliver message in DMs"
                mod_log_chan = self.bot.get_channel(552583376566091805)
                await mod_log_chan.send(msg)

    @commands.command()
    @is_guild(527887739178188830)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def autoprobate(self, ctx, status="on"):
        """Turns on or off auto probate. 
        Use "disable" to disable auto probate."""
        if status == "disable":
            ctx.guild_config.pop("auto_probate")
            await ctx.send("Auto Probate is now disabled.")
        else:
            ctx.guild_config["auto_probate"] = ctx.author.id
            await ctx.send(f"Auto Probate is now enabled\nTo turn off Auto Probate in the future, use `{ctx.prefix}autoprobate disable`")

    @commands.command()
    @is_guild(527887739178188830)
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    async def elevate(self, ctx):
        """Gains the elevated role. Use with care!"""
        target = ctx.author
        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        role = discord.Object(id=527996858908540928)

        await target.add_roles(role, reason=str(ctx.author))
        msg = f"🚑️ **Elevated**: {ctx.author.mention} | {safe_name}"

        await mod_log_chan.send(msg)
        await ctx.send(f"{target.mention} is now elevated!")

    @commands.command(aliases=['unelevate'])
    @is_guild(527887739178188830)
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    async def deelevate(self, ctx):
        """Removes the elevated role. Use with care."""
        target = ctx.author
        mod_log_chan = self.bot.get_channel(552583376566091805)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        role = discord.Object(id=527996858908540928)

        await target.remove_roles(role, reason=str(ctx.author))
        msg = f"❗️ **De-elevated**: {ctx.author.mention} | {safe_name}"

        await mod_log_chan.send(msg)
        await ctx.send(f"{target.mention} is now unelevated!")

    # These are meant to be used in one server only! 
    @commands.guild_only()
    @commands.check(check_if_botmgmt)
    @commands.group(aliases=['gh'])
    async def github(self, ctx):
        """Commands to help with GitHub things"""
        if ctx.guild.id not in config.gh_whitelisted_guilds:
            return
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.check(check_if_botmgmt)
    @github.command(aliases=['issuecomment', 'ic'])
    async def commentonissue(self, ctx, issue_number: int, *, comment: str):
        """Adds a comment to an issue"""
        if ctx.guild.id not in config.gh_whitelisted_guilds:
            return
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
    async def issuestatus(self, ctx, issue_number: int, status: str):
        """Changes the state of an issue. 
        
        Either pass 'open' or 'closed'
        """
        if ctx.guild.id not in config.gh_whitelisted_guilds:
            return
        try:
            issue = self.gh.issue(config.github_username, 
                                  config.github_repo, issue_number)
            issue.edit(state=status)
            await ctx.send(f"Done! See {issue.html_url}")
        except Exception as e:
            return await ctx.send(f"An Error Occurred! `{e}`")

    @commands.check(check_if_botmgmt)
    @github.command()
    async def closeandcomment(self, ctx, issue_number: int, *, comment: str):
        """Comments then closes an issue"""
        if ctx.guild.id not in config.gh_whitelisted_guilds:
            return
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
    async def stats(self, ctx, number: int):
        """Prints an embed with various info on an issue or pull"""
        if ctx.guild.id not in config.gh_whitelisted_guilds:
            return
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
    @github.command(aliases=['rls'])
    async def ratelimitstats(self, ctx):
        """Sends an embed with some rate limit stats"""
        if ctx.guild.id not in config.gh_whitelisted_guilds:
            return
        tmp = await ctx.send("Fetching ratelimit info...")
        rl = self.gh.rate_limit()
        embed = discord.Embed(title="Ratelimit Info")
        embed.add_field(name="Core", value=rl['resources']['core'])
        embed.add_field(name="Search", value=rl['resources']['search'])
        await tmp.delete()
        await ctx.send(embed=embed)

    @commands.check(check_if_botmgmt)
    @github.command()
    async def archivepins(self, ctx):
        """Creates a gist with the channel's pins
        
        Uses the channel that the command was invoked in."""
        if ctx.guild.id not in config.gh_whitelisted_guilds:
            return
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
    async def archivegist(self, ctx, limit: int):
        """Creates a gist with every message in channel"""
        if ctx.guild.id not in config.gh_whitelisted_guilds:
            return
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


def setup(bot):
    bot.add_cog(LightningHub(bot))