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
    interface = PaginatorInterface(bot, paginator, owner=ctx.author, timeout=300)
    await interface.send_to(ctx)

async def paginator_reg_nops(bot, ctx, size: int, page_list: list):
    paginator = commands.Paginator(prefix="", suffix="", max_size=size)
    for i in page_list:
        paginator.add_line(i)
    interface = PaginatorInterface(bot, paginator, owner=ctx.author, timeout=300)
    await interface.send_to(ctx)