"""
Lightning.py - A personal Discord bot
Copyright (C) 2020 - LightSage

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
import inspect
from typing import Any, List, Optional

import discord
from discord.ext import commands
from discord.ext.commands import converter as converters
from discord.ext.commands.core import _convert_to_bool
from discord.ext.commands.view import StringView

from lightning.commands import LightningCommand
from lightning.errors import (FlagError, FlagInputError,
                              MissingRequiredFlagArgument)


class FlagView(StringView):
    def get_word(self):
        current = self.current
        if current is None:
            return None

        result = [current]

        while not self.eof:
            current = self.get()
            if not current:
                return ''.join(result)

            if current.isspace():
                # word is over.
                return ''.join(result)

            result.append(current)


class Flag:
    """Represents a flag

    Parameters
    ----------
    *names : str
        Flag names. They must start with "-"
    help_doc : Optional[str], optional
        The help doc for the flag, by default None
    converter : Any, optional
        A converter to convert the argument passed for the flag.

        By default, converts to str
    attr_name : Optional[str], optional
        Attribute name in the namespace. If no attribute name is given, defaults to the first flag name.
    default : Optional[Any], optional
        A default argument for a flag, by default None
    required : bool, optional
        Whether the flag requires an argument, by default False
    is_bool_flag : bool, optional
        Whether the flag should be marked as a boolean flag, by default False

    Raises
    ------
    NotImplementedError
        Raised when a flag does not start with "-"
    FlagError
        Raised when a registration error occurs
    """

    __slots__ = ('names', 'help', 'converter', 'attr_name', 'default', 'required', 'is_bool_flag')

    def __init__(self, *names, help: Optional[str] = None, converter: Any = str, attr_name: Optional[str] = None,
                 default: Optional[Any] = None, required: bool = False, is_bool_flag: bool = False):
        for name in names:
            if name[0] != "-":
                raise NotImplementedError("A flag name must start with \"-\"")
        self.names = names
        self.help = help
        self.converter = converter
        attr_name = attr_name if attr_name is not None else names[0]
        self.attr_name = attr_name.strip("-").replace("-", "_")
        if self.attr_name == "rest":
            raise FlagError("\"rest\" is a reserved attribute name.")

        self.default = default
        self.required = required

        if self.default and is_bool_flag:
            raise FlagError("Boolean flags cannot have a default")

        if self.required and is_bool_flag:
            raise FlagError("Boolean flags cannot require an argument")

        self.is_bool_flag = is_bool_flag


def add_flag(*names, **kwargs):
    def deco(func):
        if isinstance(func, commands.Command):
            funct = func.callback
        else:
            funct = func

        if not hasattr(funct, '__lightning_argparser__'):
            funct.__lightning_argparser__ = Parser()

        funct.__lightning_argparser__.add_flag(Flag(*names, **kwargs))
        return func
    return deco


class Namespace:
    def __init__(self, **kwargs):
        for kwarg in kwargs:
            setattr(self, kwarg, kwargs[kwarg])

    def __contains__(self, key):
        return key in self.__dict__

    def __repr__(self):
        return "<Namespace {}>".format(' '.join(f'{name}={value}' for name, value in list(self.__dict__.items())))


class Parser:
    # TODO: Port some functionality over to discord.ext.argparse
    def __init__(self, flag_options: List[Flag] = [], *, raise_on_bad_flag: bool = True, consume_rest: bool = True):
        self.raise_on_bad_flag = raise_on_bad_flag
        self.consume_rest = consume_rest
        self._flags: dict = {}
        self._register_flags(flag_options)

    def add_flag(self, flag: Flag) -> None:
        for name in flag.names:
            if name in self._flags:
                raise FlagError(f"Flag name \"{name}\" is already registered.")
            else:
                self._flags[name] = flag

    def _register_flags(self, flags: List[Flag]) -> None:
        for flag in flags:
            self.add_flag(flag)

    def get_flag(self, flag_name: str) -> Optional[Flag]:
        return self._flags.get(flag_name, None)

    def get_all_unique_flags(self) -> set:
        return set(self._flags.values())

    async def convert_flag_type(self, flag: Flag, ctx: commands.Context, argument: Optional[str], passed_flag: str):
        converter = flag.converter
        if argument is None or argument.strip() == "":
            if flag.default is None:
                raise MissingRequiredFlagArgument(passed_flag)
            else:
                argument = flag.default

        argument = argument.strip()

        if converter is bool:
            return _convert_to_bool(argument)

        try:
            module = converter.__module__
        except AttributeError:
            pass
        else:
            if module is not None and (module.startswith('discord.') and not module.endswith('converter')):
                converter = getattr(converters, converter.__name__ + 'Converter', converter)

        try:
            if inspect.isclass(converter):
                if issubclass(converter, commands.Converter):
                    instance = converter()
                    ret = await instance.convert(ctx, argument)
                    return ret
                else:
                    method = getattr(converter, 'convert', None)
                    if method is not None and inspect.ismethod(method):
                        ret = await method(ctx, argument)
                        return ret
            elif isinstance(converter, commands.Converter):
                ret = await converter.convert(ctx, argument)
                return ret
        except commands.CommandError:
            raise
        except Exception as exc:
            raise commands.ConversionError(converter, exc) from exc

        try:
            return converter(argument)
        except commands.CommandError:
            raise
        except Exception as exc:
            try:
                name = converter.__name__
            except AttributeError:
                name = converter.__class__.__name__

            raise commands.BadArgument(f'Converting to "{name}" failed for flag "{passed_flag}".') from exc

    def _prepare_namespace(self) -> dict:
        ns = {}
        flags = self.get_all_unique_flags()
        for flag in flags:
            if flag.is_bool_flag is True:
                ns[flag.attr_name] = False
            else:
                ns[flag.attr_name] = flag.default  # More and likely it's probably None...
        return ns

    async def parse_args(self, ctx):
        view = FlagView(ctx.view.read_rest())
        view.skip_ws()
        ns = self._prepare_namespace()
        rest = []
        while not view.eof:
            word = view.get_word()
            if word is None:
                break

            stripped = word.strip()
            try:
                first = stripped[0]
            except IndexError:
                rest.append(word)
                continue

            if first == "-":
                flag = self.get_flag(stripped)
                if flag is None and self.raise_on_bad_flag is True:
                    raise FlagInputError("Invalid flag passed...")
                elif flag is None:
                    rest.append(word)
                    continue

                if flag.is_bool_flag is True:
                    ns[flag.attr_name] = True
                    continue
                view.skip_ws()
                next_arg = view.get_quoted_word()
                ns[flag.attr_name] = await self.convert_flag_type(flag, ctx, next_arg, stripped)
            else:
                rest.append(word)
                continue

        for flag in self.get_all_unique_flags():
            if ns[flag.attr_name] is None and flag.required is True:
                raise MissingRequiredFlagArgument(flag.names[0])

        ns['rest'] = ''.join(rest) or None if self.consume_rest is True else None

        return Namespace(**ns)


class FlagCommand(LightningCommand):
    """Subclass of :class:LightningCommand that implements flag parsing"""
    def __init__(self, func, **kwargs):
        super().__init__(func, **kwargs)
        if hasattr(self.callback, '__lightning_argparser__'):
            raise_bad_flag = kwargs.pop('raise_bad_flag', True)
            self.callback.__lightning_argparser__.raise_on_bad_flag = raise_bad_flag

    async def _parse_flag_args(self, ctx):
        args = await self.callback.__lightning_argparser__.parse_args(ctx)
        ctx.kwargs.update(vars(args))

    async def _parse_arguments(self, ctx):
        ctx.args = [ctx] if self.cog is None else [self.cog, ctx]
        ctx.kwargs = {}
        args = ctx.args
        kwargs = ctx.kwargs

        view = ctx.view
        iterator = iter(self.params.items())

        if self.cog is not None:
            # we have 'self' as the first parameter so just advance
            # the iterator and resume parsing
            try:
                next(iterator)
            except StopIteration:
                fmt = 'Callback for {0.name} command is missing "self" parameter.'
                raise discord.ClientException(fmt.format(self))

        # next we have the 'ctx' as the next parameter
        try:
            next(iterator)
        except StopIteration:
            fmt = 'Callback for {0.name} command is missing "ctx" parameter.'
            raise discord.ClientException(fmt.format(self))

        for name, param in iterator:
            if param.kind == param.POSITIONAL_OR_KEYWORD:
                transformed = await self.transform(ctx, param)
                args.append(transformed)
            elif param.kind == param.KEYWORD_ONLY:
                # kwarg only param denotes "consume rest" semantics
                if self.rest_is_raw:
                    converter = self._get_converter(param)
                    argument = view.read_rest()
                    kwargs[name] = await self.do_conversion(ctx, converter, argument, param)
                else:
                    kwargs[name] = await self.transform(ctx, param)
                break
            elif param.kind == param.VAR_POSITIONAL:
                if view.eof and self.require_var_positional:
                    raise commands.MissingRequiredArgument(param)
                while not view.eof:
                    try:
                        transformed = await self.transform(ctx, param)
                        args.append(transformed)
                    except RuntimeError:
                        break
            elif param.kind == param.VAR_KEYWORD:
                await self._parse_flag_args(ctx)
                break

        if not self.ignore_extra:
            if not view.eof:
                raise commands.TooManyArguments('Too many arguments passed to ' + self.qualified_name)
