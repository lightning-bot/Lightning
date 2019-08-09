from discord.ext import commands
from database import TagsTable, TagAlias
import time
import discord
import datetime
import random
from db.mod_check import check_if_at_least_has_staff_role
from utils.paginators_jsk import paginator_embed
import asyncio

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

    def find_tag(self, ctx, session, tag: str):
        # 1st look through TagAlias
        query = session.query(TagAlias).filter_by(guild_id=ctx.guild.id, tag_alias=tag).one_or_none()
        if query is None:
            # 2nd attempt look through the TagTable
            query2 = session.query(TagsTable).filter_by(guild_id=ctx.guild.id, 
                                                        tag_name=tag).one_or_none()
            if query2 is None:
                return False
            else:
                return query2
        else:
            query3 = session.query(TagsTable).filter_by(guild_id=ctx.guild.id, 
                                                        tag_name=query.tag_name).one_or_none()
            return query3

    def grab_random_tag(self, ctx, session):
        query = session.query(TagsTable).filter_by(guild_id=ctx.guild.id).all()
        # Prepare list
        querylist = []
        for t in query:
            querylist.append(t.tag_name)
        if len(querylist) == 0:
            return None
        title = random.choice(querylist)
        # Query the database again
        rand = session.query(TagsTable).filter_by(guild_id=ctx.guild.id, tag_name=title).one_or_none()
        return rand

    def check_if_alias(self, ctx, session, tag: str):
        """Dumb function that return False or the query"""
        # 1st look through TagAlias
        query = session.query(TagAlias).filter_by(guild_id=ctx.guild.id, tag_alias=tag).one_or_none()
        if query is None:
            # 2nd attempt look through the TagTable
            query2 = session.query(TagsTable).filter_by(guild_id=ctx.guild.id, 
                                                        tag_name=tag).one_or_none()
            if query2 is None:
                return False
            else:
                return False
        else:
            return query

    def check_if_tag(self, ctx, session, tag: str):
        # 1st look through TagAlias
        query = session.query(TagAlias).filter_by(guild_id=ctx.guild.id, 
                                                  tag_alias=tag).one_or_none()
        if query is None:
            # 2nd attempt look through the TagTable
            query2 = session.query(TagsTable).filter_by(guild_id=ctx.guild.id, 
                                                        tag_name=tag).one_or_none()
            if query2 is None:
                return False
            else:
                return query2
        else:
            return None

    def delete_tag(self, ctx, session, tag: str):
        # 1st look through TagAlias
        query = session.query(TagAlias).filter_by(guild_id=ctx.guild.id, tag_alias=tag).one_or_none()
        if query is None:
            # 2nd attempt look through the TagTable
            query2 = session.query(TagsTable).filter_by(guild_id=ctx.guild.id, 
                                                        tag_name=tag).one_or_none()
            if query2 is None:
                return False
            else:
                return query2
        else:
            return query

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
            session = self.bot.dbsession()
            query = self.find_tag(ctx, session, tag)
            if query is not False:
                safe_tag_content = await commands.clean_content().convert(ctx, str(query.tag_content))
                query.tag_uses = query.tag_uses + 1
                session.commit()
                session.close()
                return await ctx.send(safe_tag_content)
            else:
                session.close()
                return await ctx.send("Tag not found!")
    
    @tag.command(name='create')
    async def tag_create(self, ctx, name: TagName, *, content: str):
        """Creates a tag that's owned by you.
        
        This tag is server-specific and cannot be used in other servers.

        Note that server staff can delete your tag."""
        if len(content) > 1990:
            return await ctx.send("Reached maximum characters!")
        session = self.bot.dbsession()
        safe_tag = await commands.clean_content().convert(ctx, str(name))
        query = self.find_tag(ctx, session, name)
        if query is not False:
            return await ctx.send("Tag/Alias already exists!")
        timestamp = datetime.datetime.utcnow()
        create_tag = TagsTable(guild_id=ctx.guild.id, tag_name=name, tag_owner=ctx.author.id,
                               tag_content=content, tag_uses=0, tag_created=timestamp)
        session.merge(create_tag)
        session.commit()
        session.close()
        await ctx.send(f"✅ Created tag {safe_tag}")

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
    async def tag_alias(self, ctx, alias: TagName, tag: str):
        """Adds an alias to a tag"""
        session = self.bot.dbsession()
        query = self.find_tag(ctx, session, alias)
        if query is not False:
            return await ctx.send("Tag/Alias already exists!")
        timestamp = datetime.datetime.utcnow()
        talias = TagAlias(guild_id=ctx.guild.id, tag_name=tag, tag_alias=alias, 
                          tag_owner=ctx.author.id, tag_created=timestamp, tag_is_alias=True)
        session.merge(talias)
        session.commit()
        session.close()
        safe_tag = await commands.clean_content().convert(ctx, str(tag))
        await ctx.send(f"✅ Aliased tag: {safe_tag} to {alias}")

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
    @check_if_at_least_has_staff_role("Moderator")
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
            tagcontent = f'{tagcontent}\n{msg.attachments[0].url}'
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