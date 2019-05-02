from discord.ext import commands
import config


class Load(commands.Cog, name='Cog Management'):
    """Load, reload, unload cogs and addons"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')


    @commands.command(name='load')
    @commands.is_owner()
    async def c_load(self, ctx, *, cog: str):
        """Load a Cog."""
        log_channel = self.bot.get_channel(config.error_channel)
        try:
            self.bot.load_extension("cogs." + cog)
        except Exception as e:
            await ctx.send(f'💢 There was an error loading the cog \n**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await log_channel.send(f"{ctx.author.mention} loaded the cog `{cog}`")
            await ctx.send(f'<:LightningCheck:571376826832650240> Successfully Loaded `cogs.{cog}`')

    @commands.command(name='unload')
    @commands.is_owner()
    async def c_unload(self, ctx, *, cog: str):
        """Unloads a Cog."""
        log_channel = self.bot.get_channel(config.error_channel)

        try:
            self.bot.unload_extension("cogs." + cog)
        except Exception as e:
            await ctx.send(f'💢 There was an error unloading the cog \n***`ERROR:`** {type(e).__name__} - {e}')
        else:
            await log_channel.send(f"{ctx.author.mention} unloaded the cog `{cog}`")
            await ctx.send(f'<:LightningCheck:571376826832650240> Successfully unloaded `cogs.{cog}`')

    @commands.command(name='reload')
    @commands.is_owner()
    async def c_reload(self, ctx, *, cog: str):
        """Reload a Cog."""
        log_channel = self.bot.get_channel(config.error_channel)

        try:
            self.bot.unload_extension("cogs." + cog)
            self.bot.load_extension("cogs." + cog)
        except Exception as e:
            await ctx.send(f'💢 There was an error reloading the cog \n**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await log_channel.send(f"{ctx.author.mention} reloaded the cog `{cog}`")
            await ctx.send(f'<:LightningCheck:571376826832650240> Successfully reloaded `cogs.{cog}`')

    @commands.command(name='addonload', aliases=["addload"])
    @commands.is_owner()
    async def addon_load(self, ctx, *, addon: str):
        """Load an addon from the Addons folder"""
        log_channel = self.bot.get_channel(config.error_channel)
        
        try:
            self.bot.load_extension("addons." + addon)
        except Exception as e:
            await ctx.send(f'💢 There was an error loading the addon \n**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await log_channel.send(f"{ctx.author.mention} loaded addon `{addon}`")
            await ctx.send(f'<:LightningCheck:571376826832650240> Successfully loaded addon `addons.{addon}`')

    @commands.command(name='addonunload', aliases=["addunload"])
    @commands.is_owner()
    async def addon_unload(self, ctx, *, addon: str):
        """Unload an addon from the Addons folder"""
        log_channel = self.bot.get_channel(config.error_channel)

        try:
            self.bot.unload_extension("addons." + addon)
        except Exception as e:
            await ctx.send(f'💢 There was an error unloading the addon \n**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await log_channel.send(f"{ctx.author.mention} unloaded addon `{addon}`")
            await ctx.send(f'<:LightningCheck:571376826832650240> Successfully unloaded addon `addons.{addon}`')
    
    @commands.command(name='addonreload', aliases=["addreload"])
    @commands.is_owner()
    async def addon_reload(self, ctx, *, addon: str):
        """Reload an addon from the Addons folder"""
        log_channel = self.bot.get_channel(config.error_channel)

        try:
            self.bot.unload_extension("addons." + addon)
            self.bot.load_extension("addons." + addon)
        except Exception as e:
            await ctx.send(f'💢 There was an error reloading the addon \n**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await log_channel.send(f"{ctx.author.mention} reloaded addon `{addon}`")
            await ctx.send(f'<:LightningCheck:571376826832650240> Successfully reloaded addon `addons.{addon}`')
    

    async def cog_check(self, ctx):
        if not await ctx.bot.is_owner(ctx.author):
            raise commands.NotOwner('You aren\'t the owner of the bot. <:blobthonk:537791813990350873>')
        return True

def setup(bot):
    bot.add_cog(Load(bot))
