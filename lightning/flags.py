"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

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
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands.converter import (CONVERTER_MAPPING, Converter,
                                            _convert_to_bool)
from discord.ext.commands.view import StringView

from lightning.commands import (LightningCommand, LightningGroupCommand,
                                command, group)
from lightning.errors import (FlagError, FlagInputError,
                              MissingRequiredFlagArgument)

__all__ = ("Flag",
           "add_flag",
           "FlagParser",
           "FlagCommand",
           "HybridFlagCommand",
           "FlagGroup")


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
    help : Optional[str], optional
        The help doc for the flag, by default None
    converter : Any, optional
        A converter to convert the argument passed for the flag.

        By default, converts to str
    attribute : Optional[str], optional
        Attribute name in the namespace. If no attribute name is given, defaults to the first flag name.
    default : Optional[Any], optional
        A default argument for a flag, by default None
    required : bool, optional
        Whether the flag requires an argument, by default False
    is_bool_flag : bool, optional
        Whether the flag should be marked as a boolean flag, by default False
    consume_rest : bool, optional
        Whether the flag is a consume rest flag, by default False

    Raises
    ------
    TypeError
        Raised when a flag name does not start with "-"
    FlagError
        Raised when a bool flag has been marked as required
    """

    __slots__ = ('names', 'help', 'converter', 'attribute', 'default', 'required', 'is_bool_flag', 'consume_rest')

    def __init__(self, *names, help: Optional[str] = None, converter: Any = str, attribute: Optional[str] = None,
                 default: Optional[Any] = None, required: bool = False, is_bool_flag: bool = False,
                 consume_rest: bool = False):
        for name in names:
            if name[0] != "-":
                raise TypeError("A flag name must start with \"-\"")

        self.names = names
        self.help = help
        self.converter = converter

        attribute = attribute if attribute is not None else names[0]
        self.attribute = attribute.strip("-").replace("-", "_")

        self.default = default
        self.required = required

        # Special handling for boolean flags
        if is_bool_flag:
            self.default = bool(default)

        if self.required and is_bool_flag:
            raise TypeError("Boolean flags cannot require an argument")

        self.is_bool_flag = is_bool_flag

        # Rest flag type
        if consume_rest and is_bool_flag:
            raise TypeError("consume_rest and is_bool_flag cannot be mixed")

        self.consume_rest = consume_rest


def add_flag(*names, **kwargs):
    def deco(func):
        funct = func.callback if isinstance(func, commands.Command) else func
        if not hasattr(funct, '__lightning_argparser__'):
            funct.__lightning_argparser__ = FlagParser()

        funct.__lightning_argparser__.add_flag(Flag(*names, **kwargs))
        return func
    return deco


class Namespace(SimpleNamespace):
    def __contains__(self, key):
        return key in self.__dict__

    def __getitem__(self, key):
        return self.__dict__[key]


class FlagParser:
    def __init__(self, flag_options: List[Flag] = None, *, raise_on_bad_flag: bool = True):
        self.raise_on_bad_flag = raise_on_bad_flag
        self.consume_rest_flag: Flag = None
        self._flags: Dict[str, Flag] = {}

        self._register_flags(flag_options or [])

    def add_flag(self, flag: Flag) -> None:
        """Adds a flag to the parser

        Parameters
        ----------
        flag : Flag
            A :class:`Flag` instance
        """
        if flag.consume_rest:
            if self.consume_rest_flag is not None:
                raise FlagError("You can only define one consume_rest flag")
            self.consume_rest_flag = flag
            return

        for name in flag.names:
            if name in self._flags:
                raise FlagError(f"Flag name \"{name}\" is already registered.")
            else:
                self._flags[name] = flag

    def _register_flags(self, flags: List[Flag]) -> None:
        for flag in flags:
            self.add_flag(flag)

    def get_flag(self, name: str) -> Optional[Flag]:
        """Gets a flag

        Parameters
        ----------
        name : str
            The name of the flag to get"""
        return self._flags.get(name, None)

    def get_all_unique_flags(self) -> Set[Flag]:
        """Gets all unique flags"""
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
                converter = CONVERTER_MAPPING.get(converter, converter)

        try:
            if inspect.isclass(converter) and issubclass(converter, Converter):
                if inspect.ismethod(converter.convert):
                    return await converter.convert(ctx, argument)
                else:
                    return await converter().convert(ctx, argument)
            elif isinstance(converter, Converter):
                return await converter.convert(ctx, argument)
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

    def _prepare_raw_namespace(self) -> Dict[str, Any]:
        flags = self.get_all_unique_flags()
        return {flag.attribute: flag.default for flag in flags}

    async def parse_args(self, ctx, argument: Optional[str] = None) -> Namespace:
        argument = argument or ctx.view.read_rest()
        view = FlagView(argument.lstrip())
        ns = self._prepare_raw_namespace()
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
                    ns[flag.attribute] = True
                    continue

                view.skip_ws()
                next_arg = view.get_quoted_word()
                ns[flag.attribute] = await self.convert_flag_type(flag, ctx, next_arg, stripped)
            else:
                rest.append(word)
                continue

        for flag in self.get_all_unique_flags():
            if ns[flag.attribute] is None and flag.required is True:
                raise MissingRequiredFlagArgument(flag.names[0])

        if self.consume_rest_flag:
            ns[self.consume_rest_flag.attribute] = ''.join(rest) or None

        return Namespace(**ns)


class FlagCommand(LightningCommand):
    """Subclass of :class:LightningCommand that implements flag parsing"""
    def __init__(self, func, **kwargs):
        super().__init__(func, **kwargs)

        if hasattr(self.callback, '__lightning_argparser__'):
            parser = self.callback.__lightning_argparser__
        else:
            parser = self.callback.__lightning_argparser__ = FlagParser()

        if 'parser' in kwargs:
            # Overrides any current parser.
            parser = self.callback.__lightning_argparser__ = kwargs['parser']

        raise_bad_flag = kwargs.pop('raise_bad_flag', parser.raise_on_bad_flag)
        rest_usage_name = kwargs.pop('rest_attribute_name', None)
        flag_consume_rest = kwargs.pop('flag_consume_rest', parser.consume_rest_flag)

        if flag_consume_rest is False and rest_usage_name is not None:
            raise TypeError("Cannot specify rest_attribute_name if not consuming rest")

        if rest_usage_name:
            parser.consume_rest_flag = Flag(attribute=rest_usage_name, consume_rest=True)
        else:
            parser.consume_rest_flag = flag_consume_rest

        parser.raise_on_bad_flag = raise_bad_flag

        # Add additional flags to the parser and prevents us from stacking a bunch of decorators.
        if 'flags' in kwargs:
            # Clear _flags in order to avoid (copy) issues. Hopefully this doesn't result in anything weird.
            parser._flags.clear()
            parser._register_flags(kwargs['flags'])

    @property
    def signature(self) -> str:
        old_signature = super().signature.split()
        del old_signature[-1]

        sig = [*old_signature]

        parser: FlagParser = self.callback.__lightning_argparser__

        if parser.consume_rest_flag:
            sig.append(f"[{parser.consume_rest_flag.attribute}]")

        for flag in parser.get_all_unique_flags():
            if flag.required:
                # Required flags shouldn't have defaults?
                sig.append(f"<{flag.names[0]}>")
            elif flag.default:
                sig.append(f"[{flag.names[0]}={flag.default}]")
            else:
                sig.append(f"[{flag.names[0]}]")

        return ' '.join(sig)

    async def _parse_flag_args(self, ctx: commands.Context):
        args = await self.callback.__lightning_argparser__.parse_args(ctx)
        return args

    async def _parse_arguments(self, ctx: commands.Context):
        ctx.args = [ctx] if self.cog is None else [self.cog, ctx]
        ctx.kwargs = {}
        args = ctx.args
        kwargs = ctx.kwargs
        attachments = commands.core._AttachmentIterator(ctx.message.attachments)

        view = ctx.view
        iterator = iter(self.params.items())

        for name, param in iterator:
            if param.kind == param.POSITIONAL_OR_KEYWORD:
                transformed = await self.transform(ctx, param, attachments)
                args.append(transformed)
            elif param.kind == param.KEYWORD_ONLY:
                # kwarg only param denotes "consume rest" semantics
                kwargs[name] = await self.callback.__lightning_argparser__.parse_args(ctx)
                break
            elif param.kind == param.VAR_POSITIONAL:
                if view.eof and self.require_var_positional:
                    raise commands.MissingRequiredArgument(param)
                while not view.eof:
                    try:
                        transformed = await self.transform(ctx, param, attachments)
                        args.append(transformed)
                    except RuntimeError:
                        break
            elif param.kind == param.VAR_KEYWORD:
                await self._parse_flag_args(ctx)
                break

        if not self.ignore_extra and not view.eof:
            raise commands.TooManyArguments(f'Too many arguments passed to {self.qualified_name}')


def replace_parameters(
    parameters: Dict[str, commands.Parameter], callback, signature: inspect.Signature
) -> List[inspect.Parameter]:
    # Need to convert commands.Parameter back to inspect.Parameter so this will be a bit ugly
    params = signature.parameters.copy()
    for name, parameter in parameters.items():
        converter = parameter.converter

        # Parameter.converter properly infers from the default and has a str default
        # This allows the actual signature to inherit this property
        param = params[name].replace(annotation=converter)
        param = commands.hybrid.replace_parameter(param, converter, callback, parameter, params)

        if parameter.default is not parameter.empty:
            default = commands.hybrid._CallableDefault(parameter.default) if callable(
                parameter.default) else parameter.default
            param = param.replace(default=default)

        if isinstance(param.default, inspect.Parameter):
            # If we're here, then then it hasn't been handled yet so it should be removed completely
            param = param.replace(default=parameter.empty)

        if hasattr(callback, '__lightning_argparser__') and name == 'flags' and converter == str:
            parser: FlagParser = callback.__lightning_argparser__
            for flag in parser.get_all_unique_flags():
                transformed = inspect.Parameter(flag.attribute, parameter.kind, default=flag.default,
                                                annotation=bool if flag.is_bool_flag else flag.converter)
                param = commands.hybrid.replace_parameter(
                    transformed, transformed.annotation, callback, parameter, params)

                params[flag.attribute] = param

            if parser.consume_rest_flag:
                params[parser.consume_rest_flag.attribute] = param.replace(
                    name=parser.consume_rest_flag.attribute, default=None, annotation=str)

            del params[name]
            continue

        # Flags are flattened out and thus don't get their parameter in the actual mapping
        if hasattr(converter, '__commands_is_flag__'):
            del params[name]
            continue

        params[name] = param

    return list(params.values())


commands.hybrid.replace_parameters = replace_parameters


class HybridAppCommand(commands.hybrid.HybridAppCommand):
    async def _transform_arguments(self, interaction: discord.Interaction,
                                   namespace: app_commands.Namespace) -> Dict[str, Any]:
        transformed_values = await super()._transform_arguments(interaction, namespace)

        if hasattr(self.callback, "__lightning_argparser__"):
            parser: FlagParser = self.callback.__lightning_argparser__
            raw_ns = parser._prepare_raw_namespace()
            for f in parser.get_all_unique_flags():
                f: Flag
                try:
                    value = transformed_values.pop(f.attribute)
                except KeyError:
                    raise app_commands.CommandSignatureMismatch(self) from None
                else:
                    raw_ns[f.attribute] = value

            if parser.consume_rest_flag:
                try:
                    value = transformed_values.pop(parser.consume_rest_flag.attribute)
                except KeyError:
                    raise app_commands.CommandSignatureMismatch(self) from None
                else:
                    raw_ns[parser.consume_rest_flag.attribute] = value

            transformed_values["flags"] = Namespace(**raw_ns)

        return transformed_values


class HybridFlagCommand(commands.HybridCommand, FlagCommand):
    """
    A hybrid flag command.

    Your flags parameter must be named "flags" for the arguments to be converted.
    """
    def __init__(self, func, /, **kwargs: Any) -> None:
        super().__init__(func, **kwargs)

        if self.app_command:
            self.app_command = HybridAppCommand(self)


class FlagGroup(LightningGroupCommand, FlagCommand):
    def command(self, *args, **kwargs):
        """A shortcut decorator that invokes :func:`.command` and adds it to
        the internal command list via :meth:`~.GroupMixin.add_command`.
        Returns
        --------
        Callable[..., :class:`Command`]
            A decorator that converts the provided method into a Command, adds it to the bot, then returns it.
        """
        def decorator(func):
            kwargs.setdefault('parent', self)
            result = command(*args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator

    def group(self, *args, **kwargs):
        """A shortcut decorator that invokes :func:`.group` and adds it to
        the internal command list via :meth:`~.GroupMixin.add_command`.
        Returns
        --------
        Callable[..., :class:`Group`]
            A decorator that converts the provided method into a Group, adds it to the bot, then returns it.
        """
        def decorator(func):
            kwargs.setdefault('parent', self)
            result = group(*args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator
