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


from jishaku.paginators import PaginatorEmbedInterface, PaginatorInterface
from discord.ext import commands


async def paginator_embed(bot, ctx, embed, size: int, page_list: list):
    """Simple Function that returns a Jishaku Paginator"""
    paginator = commands.Paginator(prefix="", suffix="", max_size=size)
    for i in page_list:
        paginator.add_line(i)
    interface = PaginatorEmbedInterface(bot, paginator, owner=ctx.author,
                                        timeout=300, embed=embed)
    await interface.send_to(ctx)


async def paginator_reg(bot, ctx, size: int, page_list: list):
    paginator = commands.Paginator(max_size=size)
    for i in page_list:
        paginator.add_line(i)
    interface = PaginatorInterface(bot, paginator, owner=ctx.author,
                                   timeout=300)
    await interface.send_to(ctx)


async def paginator_reg_nops(bot, ctx, size: int, page_list: list):
    paginator = commands.Paginator(prefix="", suffix="", max_size=size)
    for i in page_list:
        paginator.add_line(i)
    interface = PaginatorInterface(bot, paginator, owner=ctx.author,
                                   timeout=300)
    await interface.send_to(ctx)
