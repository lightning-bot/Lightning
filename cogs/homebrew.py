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
import asyncpg
import discord
from discord.ext import commands
from fuzzywuzzy import fuzz, process

from utils.checks import is_staff_or_has_perms


class Homebrew(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=['nuf', 'stability'])
    @commands.bot_has_permissions(manage_webhooks=True)
    @is_staff_or_has_perms("Admin", manage_webhooks=True)
    async def nintendoupdatesfeed(self, ctx):
        """Manages the guild's configuration for Nintendo console update alerts.

        If invoked with no subcommands, this will show the current configuration."""
        if ctx.invoked_subcommand is None:
            query = "SELECT * FROM nin_updates WHERE guild_id=$1"
            ret = await self.bot.db.fetchrow(query, ctx.guild.id)
            if ret is None:
                return await ctx.send("Nintendo console updates are currently not configured!")
            webhook = discord.utils.get(await ctx.guild.webhooks(), id=ret['id'])
            if webhook is None:
                query = 'DELETE FROM nin_updates WHERE guild_id=$1'
                await self.bot.db.execute(query, ctx.guild.id)
                return await ctx.send("The webhook that sent Nintendo "
                                      "console update notifications seems to "
                                      "be deleted. Please re-configure with "
                                      f"`{ctx.prefix}nintendoupdatesfeed setup`.")
            await ctx.send("Nintendo console updates are currently "
                           f"configured to send to {webhook.channel.mention}.")

    @nintendoupdatesfeed.command(name="setup")
    @commands.bot_has_permissions(manage_webhooks=True)
    @is_staff_or_has_perms("Admin", manage_webhooks=True)
    async def nuf_configure(self, ctx, *, channel: discord.TextChannel = None):
        """Sets up a webhook in the specified channel that will send Nintendo console updates."""
        if channel is None:
            channel = ctx.channel
        try:
            webhook = await channel.create_webhook(name="Nintendo Console Updates")
        except discord.HTTPException as e:
            return await ctx.safe_send(f"Failed to create webhook. {e}")
        query = """INSERT INTO nin_updates
                   VALUES ($1, $2, $3);
                """
        try:
            await self.bot.db.execute(query, ctx.guild.id, webhook.id, webhook.token)
        except asyncpg.UniqueViolationError:
            return await ctx.send("This guild has already configured Nintendo console updates!")
        await ctx.send(f"Successfully created webhook in {channel.mention}")

    @nintendoupdatesfeed.command(name="delete")
    @commands.bot_has_permissions(manage_webhooks=True)
    @is_staff_or_has_perms("Admin", manage_webhooks=True)
    async def nuf_delete(self, ctx):
        """Deletes the configuration of Nintendo console updates."""
        query = "SELECT * FROM nin_updates WHERE guild_id=$1"
        ret = await self.bot.db.fetchrow(query, ctx.guild.id)
        if ret is None:
            return await ctx.send("Nintendo console updates are currently not configured!")
        webhook = discord.utils.get(await ctx.guild.webhooks(), id=ret['id'])
        if webhook is None:
            query = 'DELETE FROM nin_updates WHERE guild_id=$1'
            await self.bot.db.execute(query, ctx.guild.id)
            return await ctx.send("The webhook that sent Nintendo "
                                  "console update notifications seems to "
                                  "be deleted already.")
        await webhook.delete()
        query = 'DELETE FROM nin_updates WHERE guild_id=$1'
        await self.bot.db.execute(query, ctx.guild.id)
        await ctx.send("Successfully deleted webhook and configuration!")

    @commands.group(invoke_without_command=True)
    async def mod(self, ctx):
        """Gets console modding information


        If any information provided in the commands is incorrect,
        please make an issue on the GitLab repository.
        (https://gitlab.com/lightning-bot/Lightning)"""
        await ctx.send_help('mod')

    def get_match(self, word_list: list, word: str, score_cutoff: int = 60, partial=False):
        if partial:
            result = process.extractOne(word, word_list,
                                        scorer=fuzz.partial_ratio,
                                        score_cutoff=score_cutoff)
        else:
            result = process.extractOne(word, word_list,
                                        scorer=fuzz.ratio,
                                        score_cutoff=score_cutoff)
        if not result:
            return None
        return result

    @mod.group(name="3ds", aliases=['3d', '3DS', '2DS', '2ds'],
               invoke_without_command=True)
    async def mod_3ds(self, ctx, *, homebrew=None):
        """Gives information on 3DS modding."""
        if homebrew:
            commands = list(self.mod_3ds.all_commands.keys())
            match = self.get_match(commands, homebrew, 75)
            if match is not None:
                self.bot.log.info(f"Command match found {match}")
                return await ctx.invoke(self.mod_3ds.get_command(match[0]))
            # If failed to find a match, pull up the 3ds guide.
            else:
                pass
        featurelist = ["Redirect your NAND to the SD card",
                       "Run any software compatible, regardless "
                       "of if Nintendo signed it or if it was made for your region",
                       "Run game backups without requiring a physical cartridge",
                       "Redirect Software Data to the SD card, used for software modification",
                       "Customize your HOME Menu with user-created themes",
                       "Experience software the way you'd like it with screenshots and cheat codes",
                       "Backup, edit, and restore save data",
                       "Play older software using their respective emulator",
                       "Stream live gameplay to your PC wirelessly "
                       "with NTR CFW (requires a New system)"]

        em = discord.Embed(title="Nintendo 3DS Modding guide",
                           url="https://3ds.hacks.guide",
                           color=0x49151)
        em.description = ("This [guide](https://3ds.hacks.guide) will install "
                          "LumaCFW alongside boot9strap, the latest CFW")
        features = '\n- '.join(featurelist)
        em.add_field(name="Advantages to modding a 3DS", value=f"- {features}")
        em.set_footer(text='Guide by Plailect',
                      icon_url='https://pbs.twimg.com/profile_images/698944593715310592/'
                      'wTDlD5rA_400x400.png')
        await ctx.send(embed=em)

    # For the sake of reducing the code down a bit, mod_embed exists
    def mod_embed(self, title, description, social_links,
                  color, separator="\U00002022"):
        em = discord.Embed(title=title, description=description, color=color)
        links = f'\n{separator} '.join(social_links)
        em.add_field(name="Social Links", value=f'{separator} {links}')
        return em

    @mod_3ds.command(name='universal-updater', aliases=['uu', 'universalupdater'])
    async def mod_3ds_uu(self, ctx):
        """Gives information about Universal Updater"""
        social_links = ["[Github Repository](https://github.com/Universal-Team/Universal-Updater)",
                        "[Discord Server](https://discord.gg/KDJCfGF)"]
        description = "A 3DS homebrew that allows easy "\
                      "installation and updating of other 3DS homebrew"
        em = self.mod_embed("Universal-Updater",
                            description, social_links, discord.Color.green())
        em.set_thumbnail(url="https://btw.i-use-ar.ch/i/7rj8.png")
        em.set_footer(text="Made by Universal-Team (Mainly by VoltZ)")
        await ctx.send(embed=em)

    @mod.group(name="ds", aliases=['DS', 'dsi', 'DSi'],
               invoke_without_command=True)
    async def mod_ds(self, ctx, *, homebrew=None):
        """Gives information on DS modding"""
        if homebrew:
            commands = list(self.mod_ds.all_commands.keys())
            match = self.get_match(commands, homebrew, 75)
            if match is not None:
                self.bot.log.info(f"Command match found {match}")
                return await ctx.invoke(self.mod_ds.get_command(match[0]))
            # If failed to find a match, pull up the ds guide.
            else:
                pass
        features = ["Redirect your NAND to the SD card",
                    "Use normally uncompatible flashcards",
                    "Replace your home menu with TWiLightMenu++, an SD card file manager",
                    "Launch any DSiWare (out-of-region & 3DS exclusives) from "
                    "your SD card (using unlaunch)",
                    "Run homebrew applications and applications that aren't signed",
                    "Use FreeNAND to transfer configurations, sys, titles and "
                    "tickets to another Nintendo DSi from a SD NAND"]
        em = discord.Embed(title="Nintendo DSi Modding guide",
                           url="https://ds-homebrew.github.io/flashcard",
                           color=0xD6FEFF)
        # Original embed color was "16776918", search got me "D6FEFF".
        em.description = ("This [guide](https://ds-homebrew.github.io/flashcard) "
                          "will take you from a regular Nintendo "
                          "DSi to a modified console by using the Memory Pit exploit.")
        feature = '\n- '.join(features)
        em.add_field(name="Advantages to modding a Nintendo DSi", value=f"- {feature}")
        em.set_footer(text="Guide by RocketRobz")
        await ctx.send(embed=em)

    @mod_ds.command(name='flashcard')
    async def mod_dsi_cfw(self, ctx):
        """Gives the flashcard guide"""
        features = ["Run Nintendo DS game backups without requiring "
                    "a physical cartridge",
                    "Load multiple backups of Nintendo DS games "
                    "without having to carry around a bunch of cartridges",
                    "Modify your Nintendo DS game using Cheat Codes",
                    "Install Custom FirmWare on your 3DS using NTRBoot Hax"]
        embed = discord.Embed(title="Nintendo DS Flashcard guide",
                              url="https://ds-homebrew.github.io/flashcard",
                              color=0xD6FEFF)
        embed.description = ("This [guide](https://ds-homebrew.github.io/flashcard)"
                             " links to most flashcard kernels that are made "
                             "for the Nintendo DS. You can also view its "
                             "compatibility status for the Nintendo DSi and the Nintendo 3DS")
        feature = '\n- '.join(features)
        embed.add_field(name="Advantages to using a Flashcard", value=f"- {feature}")
        embed.set_footer(text="Guide by NightScript",
                         icon_url="https://btw.i-use-ar.ch/i/pglx.png")
        await ctx.send(embed=embed)

    @mod_ds.command(name='lolsnes')
    async def mod_ds_lolsnes(self, ctx):
        description = "An open-source Super Nintendo "\
                      "Entertainment System (SNES for short) "\
                      "emulator made for the Nintendo DS using a flashcard."
        links = ["[Website](http://lolsnes.kuribo64.net/)",
                 "[Github Repository](https://github.com/Arisotura/lolSnes)"]
        em = self.mod_embed("lolSnes", description, links, 0xF8E800)
        em.set_thumbnail(url="https://btw.i-use-ar.ch/i/ed1q.png")
        em.set_footer(text="Made by Arisotura",
                      icon_url="https://btw.i-use-ar.ch/i/yo0w.png")
        await ctx.send(embed=em)

    @mod_ds.command(name="nds-bootstrap", aliases=['ndsbp'])
    async def mod_ds_nds_bootstrap(self, ctx):
        """Gives information on nds-bootstrap"""
        description = "An open-source application that allows Nintendo DS"\
                      "/DSi ROMs and homebrew to be natively utilised "\
                      "rather than using an emulator. nds-bootstrap works "\
                      "on Nintendo DSi/3DS SD cards through CFW and on "\
                      "Nintendo DS through flashcarts."
        links = ["[GBATemp Thread](https://gbatemp.net/threads/nds-"
                 "bootstrap-loader-run-commercial-nds-backups-from-an-sd-card.454323/)",
                 "[Discord Server](https://discord.gg/yqSut8c)",
                 "[Github Repository](https://github.com/ahezard/nds-bootstrap)"]
        em = self.mod_embed("nds-bootstrap", description, links, 0x999A9D)
        em.set_thumbnail(url="https://btw.i-use-ar.ch/i/uroq.png")
        em.set_footer(text="Made by ahezard", icon_url="https://btw.i-use-ar.ch/i/0983.png")
        await ctx.send(embed=em)

    @mod_ds.command(name="nesDS")
    async def mod_ds_nesds(self, ctx):
        """Gives information on nesDS"""
        description = "An open-source Nintendo Entertainment "\
                      "System (NES for short) emulator for a Nintendo "\
                      "DS flashcard or a DSi/3DS SD card."
        links = ["[Github Repository](https://github.com/RocketRobz/NesDS)",
                 "([DSi Edition](https://github.com/ApacheThunder/NesDS))"]
        em = self.mod_embed("nesDS", description, links, discord.Color.red())
        em.set_footer(text="Made by loopy, FluBBa, Dwedit, tepples, "
                           "kuwanger, chishm, Mamiya, minitroopa, "
                           "huiminghao, CotoDev & ApacheThunder")
        await ctx.send(embed=em)

    @mod_ds.command(name="pkmn-chest")
    async def mod_ds_pkmn_chest(self, ctx):
        """Gives information on pkmn-chest"""
        description = "A Pokémon Bank style app that lets you store and "\
                      "edit Pokémon from the 4th and 5th generation games "\
                      "on your DS(i)."
        links = ["[Github Repository](https://github.com/Universal-Team/pkmn-chest)",
                 "[Discord Server](https://discord.gg/KDJCfGF)",
                 "[GBAtemp Thread](https://gbatemp.net/threads/release-"
                 "pkmn-chest-a-pokemon-bank-for-the-nintendo-ds-i.549249/)",
                 "[Website](https://universal-team.github.io/pkmn-chest)"]
        em = self.mod_embed("pkmn-chest", description, links, 0xBF0300)
        em.set_thumbnail(url="https://elixi.re/i/1ve4.png")
        em.set_footer(text="Made by Universal Team (Mainly by Pk11)")
        await ctx.send(embed=em)

    @mod_ds.command(name='relaunch', aliases=['buttonboot'])
    async def mod_ds_relaunch(self, ctx):
        """Gives information on Relaunch"""
        description = "A Nintendo DS(i) homebrew that allows the ability"\
                      " to launch an `.nds` file depending on which button"\
                      " you have pressed, similar to NoCash's Unlaunch."
        links = ["[Github Repository](https://github.com/Universal-Team/Relaunch)",
                 "[Discord Server](https://discord.gg/KDJCfGF)"]
        em = self.mod_embed("Relaunch", description, links, discord.Color.green())
        em.set_thumbnail(url="https://elixi.re/i/e2kb.png")
        em.set_footer(text="Made by Universal Team (Mainly by Flame)")
        await ctx.send(embed=em)

    @mod_ds.command(name='rocketvideoplayer', aliases=['rvp'])
    async def mod_ds_rocketvideoplayer(self, ctx):
        """Gives information on Rocket Video Player"""
        description = "An open-source video player powered by Rocket "\
                      "Video Technology. It can be used on a Nintendo DSi"\
                      ", a Nintendo 3DS or a Nintendo DS Flashcart by "\
                      "playing a .rvid video file from your SD card."
        links = ["[GBAtemp Thread](https://gbatemp.net/threads/release"
                 "-rocket-video-player-play-videos-with-the-ultimate-in-picture-quality.539163/)",
                 "[Github Repository](https://github.com/RocketRobz/RocketVideoPlayer/releases)",
                 "[Discord Server](https://discord.gg/yqSut8c)"]
        em = self.mod_embed("Rocket Video Player", description, links, 0xA701E9)
        em.set_thumbnail(url="https://elixi.re/i/jm7f.png")
        em.set_footer(text="Made by RocketRobz",
                      icon_url="https://elixi.re/i/7lh1.png")
        await ctx.send(embed=em)

    @mod_ds.command(name='twilightmenu++', aliases=['twlmenu', 'twilight'])
    async def mod_ds_twlmenu(self, ctx):
        """Gives information on TWiLightMenu++"""
        description = "An open-source DSi Menu upgrade/replacement allowing "\
                      "you to navigate your SD card and launch a variety of"\
                      " different applications."
        links = ["[GBATemp Thread](https://gbatemp.net/threads/"
                 "ds-i-3ds-twilight-menu-gui-for-ds-i-games-and"
                 "-ds-i-menu-replacement.472200/)",
                 "[Github Repository](https://github.com/DS-Homebrew/TWiLightMenu/releases)",
                 "[Discord Server](https://discord.gg/yqSut8c)"]
        formats = ["Nintendo DS titles",
                   "Sega Game Gear/Master System titles",
                   "NES/Famicom titles",
                   "Super NES/Famicom titles",
                   "Sega Genesis titles",
                   "(Super) Gameboy (Color) Titles",
                   # "Gameboy Advanced Titles",
                   "DSTWO plugins (requires you to have a DSTWO)",
                   "RocketVideoPlayer videos"]
        styles = ["Nintendo DSi",
                  "Nintendo 3DS",
                  "R4",
                  "Acekard/akMenu",
                  "SEGA Saturn"]
        em = self.mod_embed("TWiLightMenu++", description, links, 0xA701E9)
        em.add_field(name="Supported Formats", value=', '.join(formats), inline=False)
        stylesformat = f'\n\U00002022 '.join(styles)
        em.add_field(name="Styles", value=f"\U00002022 {stylesformat}")
        em.set_footer(text="Made by RocketRobz", icon_url="https://elixi.re/i/7lh1.png")
        await ctx.send(embed=em)

    # Only one command, useless to make it a group
    @mod.command(name='switch', aliases=['nx'])
    async def mod_switch_guide(self, ctx):
        """Gives information on Switch modding"""
        em = discord.Embed(title="Nintendo Switch Modding guide",
                           url="https://nh-server.github.io/switch-guide/",
                           color=0x00FF11)
        em.description = ("This [guide](https://nh-server.github.io/switch-guide) "
                          "will install Atmosphère, the latest and safest CFW.")
        features = ["Customize your HOME Menu with user-created themes and "
                    "splash screens",
                    "Use “ROM hacks” for games that you own",
                    "Backup, edit, and restore saves for applications",
                    "Play games for older systems with various emulators"
                    ", using RetroArch or other standalone emulators"]
        featuresformat = f'\n\U00002022 '.join(features)
        em.add_field(name="Advantages to modding a Nintendo Switch",
                     value=f"\U00002022 {featuresformat}")
        em.set_footer(text="Guide made by the Nintendo Homebrew Discord Server")
        await ctx.send(embed=em)


def setup(bot):
    bot.add_cog(Homebrew(bot))
