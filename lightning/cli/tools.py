"""
Lightning.py - A personal Discord bot
Copyright (C) 2019-2021 LightSage

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
from typing import Optional

import typer

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


def get_resolved_path(file_name: str, directory: Optional[pathlib.Path], *, suffix: str = ".py"):
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


if __name__ == "__main__":
    parser()
