import discord
from discord.ext.commands import Cog
import db.per_guild_config
import datetime

class Logger(Cog):
    """Logs user actions"""
    def __init__(self, bot):
        self.bot = bot
        print(f'Cog "{self.qualified_name}" loaded')

    # Snippet of code from Noirscape's kirigiri. Under the AGPL 3.0 License, https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/LICENSE
    async def cog_before_invoke(self, ctx):
        if db.per_guild_config.exist_guild_config(ctx.guild, "config"):
            ctx.guild_config = db.per_guild_config.get_guild_config(ctx.guild, "config")
        else:
            ctx.guild_config = {}

    async def cog_after_invoke(self, ctx):
        db.per_guild_config.write_guild_config(ctx.guild, ctx.guild_config, "config")


    @Cog.listener()
    async def on_member_join(self, member):
        await self.bot.wait_until_ready()
        if db.per_guild_config.exist_guild_config(member.guild, "config"):
            config = db.per_guild_config.get_guild_config(member.guild, "config")
            if "join_log_channel" in config:
                msg = f"<a:blobjoin:563875361402912797> **Join**: {member.mention} | "\
                 f"{member}\n"\
                 f"🗓 __Account Creation__: {member.created_at}\n"\
                 f"🕓 Account Age: {member.joined_at}\n"\
                f"🏷 __User ID__: {member.id}"
                await self.bot.get_channel(config["join_log_channel"]).send(msg)

    @Cog.listener()
    async def on_member_remove(self, member):
        await self.bot.wait_until_ready()
        if db.per_guild_config.exist_guild_config(member.guild, "config"):
            config = db.per_guild_config.get_guild_config(member.guild, "config")
            if "join_log_channel" in config:
                msg = f"<a:blobleave:566329423595438122> **Leave**: {member.mention} | "\
                    f"{member}\n"\
                    f"📅 Left Date: {datetime.datetime.utcnow()}\n"
                f"🏷 __User ID__: {member.id}"
            await self.bot.get_channel(config["join_log_channel"]).send(msg)

    @Cog.listener()
    async def on_guild_ban(self, guild, user):
        if db.per_guild_config.exist_guild_config(guild, "config"):
            config = db.per_guild_config.get_guild_config(guild, "config")
            if "event_channel" in config:
                message = f"🔨 **Ban**: {user.mention} | {user} (ID: {user.id})"
                try:
                    await self.bot.get_channel(config["event_channel"]).send(message)
                except:
                    pass

    @Cog.listener()
    async def on_member_unban(self, guild, user):
        await self.bot.wait_until_ready()
        if db.per_guild_config.exist_guild_config(guild, "config"):
            config = db.per_guild_config.get_guild_config(guild, "config")
            if "event_channel" in config:
                message = f"⚠ **Unban**: {user.mention} | {user} (ID: {user.id})."
                try:
                    await self.bot.get_channel(config["event_channel"]).send(message)
                except:
                    pass

    @Cog.listener()
    async def on_message_delete(self, message):
        await self.bot.wait_until_ready()
        if message.author.bot: # Does not log bots
            return
        if db.per_guild_config.exist_guild_config(message.guild, "config"):
            config = db.per_guild_config.get_guild_config(message.guild, "config")
            if "event_channel" in config:
                msg = "🗑️ **Message deleted**: \n"\
                      f"Author: {self.bot.escape_message(message.author.name)} "\
                      f"({message.author.id})\nChannel: {message.channel.mention}\n"\
                      f"```{message.clean_content}```" # Wrap in a code block
                # If resulting message is too long, upload to hastebin. Taken from robocop-ng which is under the MIT License.
                if len(msg) > 2000:
                    haste_url = await self.bot.haste(msg)
                    msg = f"🗑️ **Message deleted**: \nToo long: <{haste_url}>"
                try:
                    await self.bot.get_channel(config["event_channel"]).send(msg)
                except:
                    pass
        


def setup(bot):
    bot.add_cog(Logger(bot))
