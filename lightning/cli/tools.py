"""
Lightning.py - A personal Discord bot
Copyright (C) 2019-2024 LightSage

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation at version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import pathlib
import re
from collections import OrderedDict
from inspect import Parameter
from typing import List, Optional

import typer
from tabulate import tabulate

from lightning.flags import Flag

parser = typer.Typer()


cog_template = """from lightning import command, LightningCog, LightningBot


class {cls_name}(LightningCog):
    def __init__(self, bot: LightningBot):
        self.bot = bot


def setup(bot: LightningBot) -> None:
    bot.add_cog({cls_name}(bot))

"""


def get_license():
    with open("LICENSE.header", "r") as fp:
        license = fp.read()

    return license


def get_resolved_path(file_name: str, directory: Optional[pathlib.Path], *, suffix: str = ".py") -> pathlib.Path:
    if directory is None:
        path = pathlib.Path(f"{file_name}{suffix}")
    else:
        path = directory / f"{file_name}{suffix}"

    return path


@parser.command(help="Generates a new .py file with copyright added")
def newfile(file_name: str = typer.Argument(..., help="The name of the file to create"),
            directory: Optional[pathlib.Path] = typer.Option(None, help="Directory to place the generated file in",
                                                             exists=True, file_okay=False, dir_okay=True)):
    license = get_license()

    path = get_resolved_path(file_name, directory)

    with open(path, "w", encoding="utf-8") as fp:
        txt = f"{license}\n# Imports go here\n"
        fp.write(txt)

    typer.echo(f"Generated new file at {str(path)}")


@parser.command(help="Generates a new cog from a template")
def newcog(file_name: str = typer.Argument(..., help="The name of the file to create"),
           class_name: Optional[str] = typer.Option(None,
                                                    help="The name of the class to use (defaults to the file name)"),
           directory: Optional[pathlib.Path] = typer.Option(None, help="Directory to place the generated cog in",
                                                            exists=True, file_okay=False, dir_okay=True)):
    license = get_license()
    templ = cog_template.format(cls_name=class_name)

    path = get_resolved_path(file_name, directory)

    with open(path, "w", encoding="utf-8") as fp:
        fp.write(f"{license}\n{templ}")

    typer.echo(f"Created new cog with {str(path)}")


COPYRIGHT_REGEX = re.compile(r"(Copyright\s\(C\)\s[0-9].+-)[0-9].+(\s\w+)")


@parser.command()
def update_copyright(year: str = typer.Argument(..., help="The new year to write to every file"),
                     directory: pathlib.Path = typer.Option(..., help="Directory to look in",
                                                            exists=True, file_okay=False, dir_okay=True)):
    applied = []
    for file in directory.glob("**/*.py"):

        with open(file, mode="r", encoding='utf-8', newline="\n") as fp:
            w = COPYRIGHT_REGEX.sub(r"\g<1>{}\g<2>".format(year), fp.read())

        with open(file, mode="w", encoding='utf-8', newline="\n") as fp:
            fp.write(w)

        typer.echo(str(file))
        applied.append(file)

    typer.secho(f"Updated copyright for {len(applied)} files!", fg=typer.colors.GREEN)


param_name_lookup = {"HumanTime": "Time", "FutureTime": "Time"}

# This probably needs to be more detailed idk.
param_help_text = {"str": "A string", "int": "A number",
                   "Member": "Represents a user in the guild.",
                   "User": "Represents a Discord user."}


def format_command_flags(flags: List[Flag]) -> str:
    base = []
    for flag in flags:
        if flag.is_bool_flag is True:
            arg = 'No argument'
        else:
            name = flag.converter.__name__
            arg = param_name_lookup[name] if name in param_name_lookup else name

        help_text = flag.help if flag.help else "No help found..."
        base.append(f'`{", ".join(flag.names)}` ({arg}): {help_text}')
    return "\n\n\n".join(base)


def format_command_params(parameters: OrderedDict) -> str:
    base = []
    for name, param in list(parameters.items()):
        if param.annotation == Parameter.empty:  # These are str if no value
            annotation = "str"
        elif hasattr(param.annotation, "__name__"):
            annotation = param.annotation.__name__
        else:
            annotation = param.annotation.__class__.__name__
        base.append(f"\N{BULLET} **{name}**: `{annotation}`")

    if not base:
        return "None"

    return '\n\n'.join(base)


def format_command_aliases(aliases: List[str]) -> str:
    if not aliases:
        return "None"

    return f'`{", ".join([a for a in aliases])}`'


def format_subcommands(commands) -> str:
    # I'm not sure how I want this to look.
    def make_link(c):
        if c.cog:
            cog = c.cog.qualified_name.lower()
        else:
            cog = "not_categorized"

        return f'https://lightning-bot.gitlab.io/commands/{cog}/'\
            f'{c.qualified_name.replace(" ", "_")}'

    return ", ".join([f"[`{c.qualified_name}`]({make_link(c)})" for c in commands])


command_page = """## {name} {signature}

{description}

#### Aliases

{aliases}


#### Arguments

{params}

{flags}

{subcmds}
"""

flag_page = """#### Flags

{flags}
"""

subcmds_page = """#### Subcommands

{subcmds}
"""


@parser.command()
def build_command_docs():
    """Builds documentation for commands and stores them in the build directory"""
    from lightning import LightningBot
    bot = LightningBot()
    for command in bot.walk_commands():
        description = command.description or command.help
        flag_fmt = ""
        signature = command.signature or command.usage
        subcmd_fmt = ""

        if hasattr(command.callback, "__lightning_argparser__"):
            flags = command.callback.__lightning_argparser__.get_all_unique_flags()
            flag_fmt = flag_page.format(flags=format_command_flags(flags))

        # This is a group
        if hasattr(command, "commands"):
            subcmd_fmt = subcmds_page.format(subcmds=format_subcommands(command.commands))

        fmt = command_page.format(name=command.qualified_name, signature=signature.strip() or "",
                                  description=description.replace("\n", "<br>") if description else "",
                                  aliases=format_command_aliases(command.aliases),
                                  params=format_command_params(command.clean_params),
                                  flags=flag_fmt, subcmds=subcmd_fmt)

        fname = command.qualified_name.replace(" ", "_")

        if command.cog:
            cog = command.cog.qualified_name.lower()
        else:
            cog = "not_categorized"

        path = pathlib.Path(f"build/docs/commands/{cog}/")
        path.mkdir(parents=True, exist_ok=True)
        path = path / pathlib.Path(f"{fname}.md")
        with path.open("w", encoding="utf-8") as fp:
            fp.write(fmt)

        typer.echo(f"Built {command.qualified_name} page ({str(path)})")

    typer.echo("Built all command pages!")


@parser.command()
def build_cog_docs():
    """Builds documentation pages for cogs and stores them in the build directory"""
    from lightning import LightningBot
    bot = LightningBot()
    cogs = sorted(bot.cogs.values(), key=lambda c: c.qualified_name)
    for cog in cogs:
        cmds = []

        for command in sorted(cog.walk_commands(), key=lambda c: c.qualified_name):
            aliases = ' '.join("`{}`".format(r) for r in command.aliases) or "None"
            signature = command.signature or command.usage
            usage = f".{command.qualified_name}"
            if signature:
                usage += f" {signature}"

            if command.cog:
                cog_name = command.cog.qualified_name.lower()
            else:
                cog_name = "not_categorized"

            description = command.help.replace('\n', '<br>') if command.help else None

            link = f'https://lightning-bot.gitlab.io/commands/{cog_name}/'\
                f'{command.qualified_name.lower().replace(" ", "_")}'

            cmds.append((f"[{command.qualified_name}]({link})", aliases, description, f"`{usage}`"))

        path = pathlib.Path(f"build/docs/commands/{cog.qualified_name.lower()}")
        path.mkdir(parents=True, exist_ok=True)
        path = path / pathlib.Path("index.md")  # There should never be a command called "index"

        desc = (cog.qualified_name, cog.description, tabulate(cmds,
                headers=("Name", "Aliases", "Description", "Usage"), tablefmt="github"))
        fmt = "# {}\n{}\n\n{}\n\n".format(desc[0], desc[1], desc[2])
        with path.open("w", encoding="utf-8") as fp:
            fp.write(fmt)

        typer.echo(f"Built {cog.qualified_name} page ({str(path)})")

    typer.echo("Built all cog pages!")


@parser.command()
def builddocs():
    """Builds all documentation"""
    build_cog_docs()
    build_command_docs()

    typer.echo("Built all pages!")


if __name__ == "__main__":
    parser()
