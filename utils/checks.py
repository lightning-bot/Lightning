from discord.ext import commands
import config

def is_guild(guild_id):
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.guild.id == guild_id:
            return True
    return commands.check(predicate)

def is_git_whitelisted(ctx):
    if not ctx.guild:
        return False
    guild = (ctx.guild.id in config.gh_whitelisted_guilds)
    return (guild)