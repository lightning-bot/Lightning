from discord.ext import commands


class Load(commands.Cog, name='Cog Management'):
    """Load, reload, unload cogs and addons"""
    def __init__(self, bot):
        self.bot = bot
        print(f'Cog "{self.qualified_name}" loaded')

    # Hidden means it won't show up on the default help.

    @commands.command(name='load', hidden=True)
    @commands.is_owner()
    async def c_load(self, ctx, *, cog: str):
        """Load a Cog.
        e.g: owner"""

        try:
            self.bot.load_extension("cogs." + cog)
        except Exception as e:
            await ctx.send(f'💢 There was an error loading the cog \n**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('✅ Successfully Loaded Cog')

    @commands.command(name='unload', hidden=True)
    @commands.is_owner()
    async def c_unload(self, ctx, *, cog: str):
        """Unloads a Cog.
        e.g: owner"""

        try:
            self.bot.unload_extension("cogs." + cog)
        except Exception as e:
            await ctx.send(f'💢 There was an error unloading the cog \n***`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('✅ Successfully unloaded cog')

    @commands.command(name='reload', hidden=True)
    @commands.is_owner()
    async def c_reload(self, ctx, *, cog: str):
        """Reload a Cog.
        e.g: owner"""

        try:
            self.bot.unload_extension("cogs." + cog)
            self.bot.load_extension("cogs." + cog)
        except Exception as e:
            await ctx.send(f'💢 There was an error reloading the cog \n**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('✅ Successfully reloaded cog')

    @commands.command(name='addonload', aliases=["addload"])
    @commands.is_owner()
    async def addon_load(self, ctx, *, addon: str):
        """Load an addon from the Addons folder"""
        try:
            self.bot.load_extension("addons." + addon)
        except Exception as e:
            await ctx.send(f'💢 There was an error loading the addon \n**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send(f'✅ Successfully loaded addon `addons.{addon}`')

    @commands.command(name='addonunload', aliases=["addunload"])
    @commands.is_owner()
    async def addon_unload(self, ctx, *, addon: str):
        """Unload an addon from the Addons folder"""
        try:
            self.bot.unload_extension("addons." + addon)
        except Exception as e:
            await ctx.send(f'💢 There was an error unloading the addon \n**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send(f'✅ Successfully unloaded addon `addons.{addon}`')
    
    @commands.command(name='addonreload', aliases=["addreload"])
    @commands.is_owner()
    async def addon_reload(self, ctx, *, addon: str):
        """Reload an addon from the Addons folder"""
        try:
            self.bot.unload_extension("addons." + addon)
            self.bot.load_extension("addons." + addon)
        except Exception as e:
            await ctx.send(f'💢 There was an error reloading the addon \n**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send(f'✅ Successfully reloaded addon `addons.{addon}`')
    

    async def cog_check(self, ctx):
        if not await ctx.bot.is_owner(ctx.author):
            raise commands.NotOwner('You aren\'t the owner of the bot. <:blobthonk:537791813990350873>')
        return True

def setup(bot):
    bot.add_cog(Load(bot))