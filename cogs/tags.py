# Lightning.py - The Successor to Lightning.js
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
#
# In addition, clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version

from discord.ext import commands
from database import TagsTable, TagAlias
import discord
import datetime
import random
from utils.checks import has_staff_role
from utils.paginators_jsk import paginator_embed
import asyncio
import asyncpg

# R.Danny's Tag Converter.
# https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/tags.py#L93
class TagName(commands.clean_content):
    def __init__(self, *, lower=False):
        self.lower = lower
        super().__init__()

    async def convert(self, ctx, argument):
        converted = await super().convert(ctx, argument)
        lower = converted.lower().strip()
        first_word, _, _ = lower.partition(' ')
        root = ctx.bot.get_command('tag')
        if first_word in root.all_commands:
            await ctx.send("This tag name starts with a reserved word.")
            raise commands.BadArgument('This tag name starts with a reserved word.')

        return converted if not self.lower else lower

class Tags(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tags_making = {}

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    async def get_tag(self, ctx, name):
        query = """SELECT tag_name, tag_content
                FROM tags WHERE guild_id=$1 
                AND tag_name=$2
                INNER JOIN tag_aliases ON tag_aliases.tag_points_to = tags.tag_name;
                """
        async with self.bot.db.acquire() as con:
            tag = await con.fetchrow(query, ctx.guild.id, name)
        if tag:
            return tag
        else:
            raise Exception("Could not find that tag") 

    async def create_tag(self, ctx, name, content):
        query = """INSERT INTO tags (guild_id, tag_name, tag_content, tag_author, created_at)
                   VALUES ($1, $2, $3, $4, $5);
                """

        async with ctx.acquire():
            tr = ctx.db.transaction()
            await tr.start()

            try:
                await ctx.db.execute(query, ctx.guild.id, name, content, ctx.author.id, ctx.message.created_at)
            except asyncpg.UniqueViolationError:
                await tr.rollback()
                await ctx.send('This tag already exists.')
            except:
                await tr.rollback()
                await ctx.send('Could not create tag.')
            else:
                await tr.commit()
                await ctx.send(f'Tag {name} successfully created.')

    async def tag_list(self, ctx, session, user=False, **kwargs):
        """Function to get all tags and return them back"""
        if user is False:
            query = session.query(TagsTable).filter_by(guild_id=ctx.guild.id).all()
            if len(query) == 0:
                return None
            return query
        if user is True:
            self.owner = kwargs.pop('owner', None)
            owner = self.owner
            query = session.query(TagsTable).filter_by(guild_id=ctx.guild.id, 
                                                       tag_owner=owner).all()
            if len(query) == 0:
                return None
            return query

    def tag_being_made(self, gid, tag):
        try:
            bruh = self.tags_making[gid]
        except KeyError:
            return False
        else:
            return tag in bruh
    
    def add_tag_in_progress(self, gid, tag):
        tg = self.tags_making.setdefault(gid, set())
        tg.add(tag)

    def remove_tag_in_progress(self, gid, tag):
        try:
            tg = self.tags_making[gid]
        except KeyError:
            return
        
        tg.discard(tag)
        if len(tg) == 0:
            del self.tags_making[gid]
        
    @commands.group(invoke_without_command=True)
    async def tag(self, ctx, *, tag: TagName=None):
        if tag is None:
            return await ctx.send_help(ctx.command)
        if ctx.invoked_subcommand is None:
            try:
                tag = await self.get_tag(ctx, tag)
            except Exception as e:
                return await ctx.send(e)

            await ctx.send(tag['tag_content'])
            query = "UPDATE tags SET uses = uses + 1 WHERE name = $1 AND guild_id=$2"
            async with self.bot.db.acquire() as con:
                await con.execute(query, tag['tag_name'])
            
    
    @tag.command(name='create')
    async def tag_create(self, ctx, name: TagName, *, content: commands.clean_content):
        """Creates a tag that's owned by you.
        
        This tag is server-specific and cannot be used in other servers.

        Note that server staff can delete your tag."""
        if len(content) > 1990:
            return await ctx.send("Reached maximum characters!")
        safe_name = await commands.clean_content().convert(ctx, str(name))
        await self.create_tag(ctx, safe_name, content)
        await ctx.send(f"✅ Created tag {safe_name}")

    @tag.command(name='info')
    async def tag_info(self, ctx, *, tag: str):
        """Gives information on a certain tag or alias"""
        session = self.bot.dbsession()
        query = self.find_tag(ctx, session, tag)
        achk = self.check_if_alias(ctx, session, tag)
        if query is False:
            session.close()
            return await ctx.send("Tag doesn\'t exist!")
        embed = discord.Embed(title=f"Info for {tag}", color=discord.Color(0x0fef10))
        if achk is False:
            tag_creator = await self.bot.fetch_user(query.tag_owner)
            embed.add_field(name="Owner", value=tag_creator.mention)
            embed.add_field(name="Uses", value=query.tag_uses)
            embed.set_author(name=tag_creator, icon_url=tag_creator.avatar_url)
            embed.set_footer(text="Tag created at")
            embed.timestamp = query.tag_created
            session.close()
            return await ctx.send(embed=embed)
        elif achk.tag_is_alias is not False:
            tag_creator = await self.bot.fetch_user(achk.tag_owner)
            embed.set_author(name=tag_creator, icon_url=tag_creator.avatar_url)
            embed.add_field(name="Owner", value=tag_creator.mention)
            embed.add_field(name="Alias for Tag Name:", value=achk.tag_name)
            embed.set_footer(text="Alias created at")
            embed.timestamp = achk.tag_created
            session.close()
            return await ctx.send(embed=embed)

    @tag.command(name='alias')
    async def tag_alias(self, ctx, alias: TagName, *, tag: str):
        """Adds an alias to a tag"""
        query = """INSERT INTO tag_aliases (guild_id, tag_name, tag_author, tag_points_to)
                   SELECT $1, $4, tag_lookup.location_id, tag_lookup.tag_id
                   FROM tag_lookup
                   WHERE tag_lookup.location_id=$3 AND LOWER(tag_lookup.name)=$2;
                """

        try:
            status = await ctx.db.execute(query, ctx.guild.id, tag.lower(), ctx.author.id, alias)
        except asyncpg.UniqueViolationError:
            await ctx.send('A tag with this name already exists.')
        else:
            # The status returns INSERT N M, where M is the number of rows inserted.
            if status[-1] == '0':
                await ctx.send(f'A tag with the name of "{tag}" does not exist.')
            else:
                await ctx.safe_send(f'✅ Tag alias "{alias}" that points to "{tag}" successfully created.')

    @tag.command(name='random')
    async def tag_random(self, ctx):
        """Gets a random tag"""
        session = self.bot.dbsession()
        tag = self.grab_random_tag(ctx, session)
        if tag is None:
            return await ctx.send("There are no tags in this guild!")
        safe_tag_content = await commands.clean_content().convert(ctx, str(tag.tag_content))
        safe_tag = await commands.clean_content().convert(ctx, str(tag.tag_name))
        tag.tag_uses = tag.tag_uses + 1
        session.commit()
        session.close()
        await ctx.send(f"Tag: `{safe_tag}`\n{safe_tag_content}")

    @tag.command(name='transfer')
    async def tag_transfer(self, ctx, member: discord.Member, *, tag_name: str):
        """Transfers a tag's owner to another person. 

        You must own the tag to transfer it"""
        session = self.bot.dbsession()
        tagchk = self.check_if_tag(ctx, session, tag_name)
        if tagchk is None:
            session.close()
            return await ctx.send("You cannot transfer ownership of a tag alias!")
        tag = self.find_tag(ctx, session, tag_name)
        if tag is False:
            session.close()
            return await ctx.send("No Tag Found!")
        elif tag.tag_owner != ctx.author.id:
            safe_tag = await commands.clean_content().convert(ctx, str(tag.tag_name))
            session.close()
            return await ctx.send(f'A tag with the name of "{safe_tag}" is not owned by you!')
        tag.tag_owner = member.id
        session.commit()
        session.close()
        safe_name = await commands.clean_content().convert(ctx, str(member))
        await ctx.send(f"Transferred tag ownership to {safe_name}.")

    @tag.command(name="purge")
    @has_staff_role("Moderator")
    async def tag_purge(self, ctx, member: discord.Member):
        """Removes all tags made by a member. Moderator+"""
        session = self.bot.dbsession()
        safe_name = await commands.clean_content().convert(ctx, str(member))
        query = session.query(TagsTable).filter_by(guild_id=ctx.guild.id, tag_owner=member.id)
        querymem = query.all()
        count = 0
        names = []
        for t in querymem:
            count += 1
            names.append(t.tag_name)
        if count == 0:
            return await ctx.send(f"{safe_name} does not have any tags.")
        query.delete()
        # Now process our names and delete them from aliases
        for nm in names:
            session.query(TagAlias).filter_by(guild_id=ctx.guild.id, tag_name=nm).delete()
        session.commit()
        session.close()
        await ctx.send(f"Deleted {count} tags from {safe_name}")

    @tag.command(name="purgeid")
    @check_if_at_least_has_staff_role("Moderator")
    async def tag_purge_id(self, ctx, member_id: int):
        """Removes all tags made by member's ID. Moderator+"""
        try:
            member = await self.bot.fetch_user(member_id)
        except discord.NotFound:
            return await ctx.send("Invalid ID!")
        session = self.bot.dbsession()
        safe_name = await commands.clean_content().convert(ctx, str(member))
        query = session.query(TagsTable).filter_by(guild_id=ctx.guild.id, tag_owner=member.id)
        querymem = query.all()
        count = 0
        names = []
        for t in querymem:
            count += 1
            names.append(t.tag_name)
        if count == 0:
            return await ctx.send(f"{safe_name} does not have any tags.")
        query.delete()
        # Now process our names and delete them from aliases
        for nm in names:
            session.query(TagAlias).filter_by(guild_id=ctx.guild.id, tag_name=nm).delete()
        session.commit()
        session.close()
        await ctx.send(f"Deleted {count} tags from {safe_name}")

    @tag.command(name="claim")
    async def tag_claim(self, ctx, *, tag_name: str):
        """Claims an unclaimed tag.

        An unclaimed tag is a tag that has no owner because the 
        tag owner have left the server."""
        session = self.bot.dbsession()
        query = self.find_tag(ctx, session, tag_name)
        if query is False:
            return await ctx.send("Tag doesn\'t exist!")
        try:
            member = ctx.guild.get_member(query.tag_owner) or await ctx.guild.fetch_member(query.tag_owner)
        except discord.NotFound:
            member = None
        
        if member is not None:
            return await ctx.send("❌ Tag owner is still in the server!")
        
        query.tag_owner = ctx.author.id
        session.commit()
        session.close()
        await ctx.send(f"Transferred tag ownership to you ({ctx.author})")

    @tag.command(name="raw")
    async def tag_raw(self, ctx, *, tag_name: str):
        """Gets the raw contents of a tag"""
        session = self.bot.dbsession()
        query = self.find_tag(ctx, session, tag_name)
        if query is False:
            return await ctx.send("Tag doesn\'t exist!")
        clean_md = discord.utils.escape_markdown(query.tag_content)
        safe_tag_content = await commands.clean_content().convert(ctx, str(clean_md))
        await ctx.send(f"```{safe_tag_content}```")

    @tag.command(name="edit")
    async def tag_edit(self, ctx, tag_name: str, *, content: str):
        """Edits the contents of a tag you own."""
        session = self.bot.dbsession()
        query = self.find_tag(ctx, session, tag_name)
        check_iftag = self.check_if_tag(ctx, session, tag_name)
        if query is False:
            return await ctx.send("Tag doesn\'t exist!")
        elif check_iftag is None:
            return await ctx.send("Aliases cannot be edited!")
        elif len(content) > 1990:
            return await ctx.send("Reached maximum characters!")
        elif query.tag_owner != ctx.author.id:
            safe_tag = await commands.clean_content().convert(ctx, str(query.tag_name))
            return await ctx.send(f'A tag with the name of "{safe_tag}" is not owned by you!')
        query.tag_content = content
        session.commit()
        session.close()
        await ctx.send("✅ Successfully edited tag!")

    @tag.command(name="all")
    async def tag_list_all(self, ctx):
        """Lists all the tags for a guild"""
        session = self.bot.dbsession()
        result = await self.tag_list(ctx, session, user=False)
        if result is None:
            session.close()
            return await ctx.send("This server has no tags!")
        # Prepare to paginate
        pages = [f""]
        for r in result:
            pages.append(f"{r.tag_name}")
        # Prepare our embed and paginate
        embed = discord.Embed(title=f"All Tags for {ctx.guild.name}", color=discord.Color(0x60c22b))
        await paginator_embed(self.bot, ctx, embed, size=200, page_list=pages)

    @tag.command(name="list")
    async def tag_list_member(self, ctx, member: discord.Member=None):
        """Lists all the tags for a member"""
        if member is None:
            member = ctx.author
        session = self.bot.dbsession()
        result = await self.tag_list(ctx, session, user=True, owner=member.id)
        if result is None:
            session.close()
            return await ctx.send("You haven\'t created any tags in this guild!")
        # Prepare to paginate
        pages = [f""]
        for r in result:
            pages.append(f"{r.tag_name}")
        # Prepare our embed and paginate
        embed = discord.Embed(title=f"All Tags for {member}", color=discord.Color(0x60c22b))
        await paginator_embed(self.bot, ctx, embed, size=200, page_list=pages)

    @tag.command(name="delete")
    async def tag_delete(self, ctx, *, tag_name: str):
        """Deletes a tag"""
        session = self.bot.dbsession()
        query = self.delete_tag(ctx, session, tag_name)
        tagchk = self.check_if_alias(ctx, session, tag_name)
        print(repr(query.tag_owner))
        if query is False:
            return await ctx.send("Tag doesn\'t exist!")
        if query.tag_owner != ctx.author.id:
            if tagchk is False:
                safe_tag = await commands.clean_content().convert(ctx, str(query.tag_name))
                msg = f'A tag with the name "{safe_tag}" is not owned by you!'
            if tagchk is not False:
                safe_tag = await commands.clean_content().convert(ctx, str(tagchk.tag_alias))
                msg = f'An alias with the name "{safe_tag}" is not owned by you!'
            session.close()
            return await ctx.send(msg)
        session.delete(query)
        if tagchk is False:
            msg = 'Successfully deleted tag'
            # Now we run through tagaliases and delete ones that match our tag
            session.query(TagAlias).filter_by(guild_id=ctx.guild.id, tag_name=tag_name).delete()
        else:
            msg = 'Successfully deleted alias'
        session.commit()
        session.close()
        await ctx.send(msg)

    @tag.command(name="make")
    async def tag_make(self, ctx):
        """Interactively makes a tag"""
        await ctx.send('Hello. What would you like the tag\'s name to be?')

        def check(msg):
            return msg.author == ctx.author and ctx.channel == msg.channel

        try:
            msg = await self.bot.wait_for('message', timeout=30.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send('You took long. Bye.')

        tagname = msg.content

        if self.tag_being_made(ctx.guild.id, tagname):
            return await ctx.send('This tag is currently being made by someone. '
                                  f'Redo the command "{ctx.prefix}tag make" to retry.')

        # Check to see if that tag exists already
        session = self.bot.dbsession()
        queried = self.find_tag(ctx, session, tagname)
        if queried is not False:
            return await ctx.send("Tag/alias already exists!")

        self.add_tag_in_progress(ctx.guild.id, tagname)
        safe_tag = await commands.clean_content().convert(ctx, str(tagname))

        await ctx.send(f'Cool. The tag\'s name is {safe_tag}. What would you like to set as'
                        " the tag\'s content?\n"
                       f'**You can type `{ctx.prefix}cancel` to discard the tag.**')
        
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=300.0)
        except asyncio.TimeoutError:
            self.remove_tag_in_progress(ctx.guild.id, tagname)
            return await ctx.send('You took too long. Bye.')

        if msg.content == f'{ctx.prefix}cancel':
            self.remove_tag_in_progress(ctx.guild.id, tagname)
            return await ctx.send('Cancelling.')
        
        if msg.attachments:
            tagcontent = f'{msg.content}\n{msg.attachments[0].url}'
        else:
            tagcontent = msg.content

        timestamp = datetime.datetime.utcnow()
        create_tag = TagsTable(guild_id=ctx.guild.id, tag_name=tagname, tag_owner=ctx.author.id,
                               tag_content=tagcontent, tag_uses=0, tag_created=timestamp)
        session.merge(create_tag)
        session.commit()
        session.close()
        await ctx.send(f"✅ Created tag {safe_tag}")

def setup(bot):
    bot.add_cog(Tags(bot))