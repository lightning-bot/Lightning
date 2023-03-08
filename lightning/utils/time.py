"""
Lightning.py - A Discord bot
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

# ShortTime, HumanTime, Time, FutureTime, UserFriendlyTime code is provided by Rapptz under the MIT License
# Copyright ©︎ 2015 Rapptz
# https://github.com/Rapptz/RoboDanny/blob/245f2aa4a5caed6861b581c262dafc6835863fe2/cogs/utils/time.py
from __future__ import annotations

import datetime
import re
from typing import Optional

import parsedatetime as pdt
from dateutil.relativedelta import relativedelta
from discord.ext import commands
from discord.utils import format_dt

from lightning.formatters import human_join, plural


class ShortTime:
    compiled = re.compile("""(?:(?P<years>[0-9])(?:years?|y))?             # e.g. 2y
                             (?:(?P<months>[0-9]{1,2})(?:months?|mo))?     # e.g. 2months
                             (?:(?P<weeks>[0-9]{1,4})(?:weeks?|w))?        # e.g. 10w
                             (?:(?P<days>[0-9]{1,5})(?:days?|d))?          # e.g. 14d
                             (?:(?P<hours>[0-9]{1,5})(?:hours?|h))?        # e.g. 12h
                             (?:(?P<minutes>[0-9]{1,5})(?:minutes?|m))?    # e.g. 10m
                             (?:(?P<seconds>[0-9]{1,5})(?:seconds?|s))?    # e.g. 15s
                          """, re.VERBOSE)

    def __init__(self, argument: str, *, now: Optional[datetime.datetime] = None):
        match = self.compiled.fullmatch(argument)
        if match is None or not match.group(0):
            raise commands.BadArgument('Invalid time provided')

        data = {k: int(v) for k, v in match.groupdict(default=0).items()}
        now = now or datetime.datetime.now(datetime.timezone.utc)
        # Expose relativedelta as we may need this
        self.delta = relativedelta(**data)
        self.dt = now + relativedelta(**data)

    @classmethod
    async def convert(cls, ctx, argument):
        return cls(argument, now=ctx.message.created_at)


class HumanTime:
    calendar = pdt.Calendar(version=pdt.VERSION_CONTEXT_STYLE)

    def __init__(self, argument: str, *, now=None):
        now = now or datetime.datetime.now(datetime.timezone.utc)
        dt, status = self.calendar.parseDT(argument, sourceTime=now, tzinfo=datetime.timezone.utc)
        if not status.hasDateOrTime:
            raise commands.BadArgument('Invalid time provided, try e.g. "tomorrow" or "3 days"')

        if not status.hasTime:
            # replace it with the current time
            dt = dt.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)

        self.dt = dt
        self._past = dt < now

    @classmethod
    async def convert(cls, ctx, argument: str):
        return cls(argument, now=ctx.message.created_at)


class Time(HumanTime):
    def __init__(self, argument: str, *, now=None):
        try:
            o = ShortTime(argument, now=now)
        except Exception:
            super().__init__(argument)
        else:
            self.delta = o.delta
            self.dt = o.dt
            self._past = False


class FutureTime(Time):
    def __init__(self, argument, *, now=None):
        super().__init__(argument, now=now)

        if self._past:
            raise commands.BadArgument('This time is in the past')


# Should avoid our need to copy the UserFriendlyTime converter
class UserFriendlyTimeResult:
    def __init__(self, dt: datetime.datetime) -> None:
        self.dt = dt
        self.arg: str = ""

    async def check_constraints(self, ctx, time_cls: UserFriendlyTime, now: datetime.datetime, remaining: str):
        if self.dt < now:
            raise commands.BadArgument('This time is in the past.')

        if not remaining:
            if time_cls.default is None:
                raise commands.BadArgument('Missing argument after the time.')
            remaining = time_cls.default

        if time_cls.converter is not None:
            self.arg = await time_cls.converter.convert(ctx, remaining)
        else:
            self.arg = remaining
        return self


class UserFriendlyTime(commands.Converter):
    """That way quotes aren't absolutely necessary."""

    def __init__(self, converter=None, *, default=None):
        if isinstance(converter, type) and issubclass(converter, commands.Converter):
            converter = converter()

        if converter is not None and not isinstance(converter, commands.Converter):
            raise TypeError('commands.Converter subclass necessary.')

        self.converter = converter
        self.default = default

    async def convert(self, ctx, argument: str) -> UserFriendlyTimeResult:
        calendar = HumanTime.calendar
        regex = ShortTime.compiled
        now = ctx.message.created_at

        match = regex.match(argument)
        if match is not None and match.group(0):
            data = {k: int(v) for k, v in match.groupdict(default=0).items()}
            remaining = argument[match.end():].strip()
            result = UserFriendlyTimeResult(now + relativedelta(**data))
            await result.check_constraints(ctx, self, now, remaining)
            return result

        if match is None or not match.group(0):
            if match := re.compile(
                r'<t:(?P<timestamp>[0-9]+)(?:\:[tTdDfFR])?>'
            ).fullmatch(argument):
                remaining = argument[match.end():].strip()
                result = UserFriendlyTimeResult(datetime.datetime.fromtimestamp(int(match['timestamp']),
                                                tz=datetime.timezone.utc))
                await result.check_constraints(ctx, self, now, remaining)
                return result

        # apparently nlp does not like "from now"
        # it likes "from x" in other cases though so let me handle the 'now' case
        if argument.endswith('from now'):
            argument = argument[:-8].strip()

        if argument[:2] == 'me' and argument[:6] in ('me to ', 'me in ', 'me at '):
            argument = argument[6:]

        elements = calendar.nlp(argument, sourceTime=now)
        if elements is None or len(elements) == 0:
            raise commands.BadArgument('Invalid time provided, try e.g. "tomorrow" or "3 days".')

        # handle the following cases:
        # "date time" foo
        # date time foo
        # foo date time

        # first the first two cases:
        dt, status, begin, end, dt_string = elements[0]

        if not status.hasDateOrTime:
            raise commands.BadArgument('Invalid time provided, try e.g. "tomorrow" or "3 days".')

        if begin not in (0, 1) and end != len(argument):
            raise commands.BadArgument('Time is either in an inappropriate location, which '
                                       'must be either at the end or beginning of your input, '
                                       'or I just flat out did not understand what you meant. Sorry.')

        if not status.hasTime:
            # replace it with the current time
            dt = dt.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)

        # if midnight is provided, just default to next day
        if status.accuracy == pdt.pdtContext.ACU_HALFDAY:
            dt = dt.replace(day=now.day + 1)

        if dt.tzinfo is None:
            dt = add_tzinfo(dt)

        remaining = ''

        if begin in (0, 1):
            if begin == 1:
                # check if it's quoted:
                if argument[0] != '"':
                    raise commands.BadArgument('Expected quote before time input...')

                if end >= len(argument) or argument[end] != '"':
                    raise commands.BadArgument('If the time is quoted, you must unquote it.')

                remaining = argument[end + 1:].lstrip(' ,.!')
            else:
                remaining = argument[end:].lstrip(' ,.!')
        elif len(argument) == end:
            remaining = argument[:begin].strip()

        result = UserFriendlyTimeResult(dt)
        await result.check_constraints(ctx, self, now, remaining)
        return result


def natural_timedelta(dt, *, source=None, accuracy=3, brief=False, suffix=True) -> str:
    now = source or datetime.datetime.now(datetime.timezone.utc)
    # We're just going to add tzinfo to both if we have to
    if dt.tzinfo is None:
        dt = add_tzinfo(dt)

    if now.tzinfo is None:
        now = add_tzinfo(now)

    # Microsecond free zone
    now = now.replace(microsecond=0)
    dt = dt.replace(microsecond=0)

    # This implementation uses relativedelta instead of the much more obvious
    # divmod approach with seconds because the seconds approach is not entirely
    # accurate once you go over 1 week in terms of accuracy since you have to
    # hardcode a month as 30 or 31 days.
    # A query like "11 months" can be interpreted as "!1 months and 6 days"
    if dt > now:
        delta = relativedelta(dt, now)
        suffix = ''
    else:
        delta = relativedelta(now, dt)
        suffix = ' ago' if suffix else ''

    attrs = [
        ('year', 'y'),
        ('month', 'mo'),
        ('day', 'd'),
        ('hour', 'h'),
        ('minute', 'm'),
        ('second', 's'),
    ]

    output = []
    for attr, brief_attr in attrs:
        elem = getattr(delta, f'{attr}s')
        if not elem:
            continue

        if attr == 'day':
            if weeks := delta.weeks:
                elem -= weeks * 7
                if not brief:
                    output.append(format(plural(weeks), 'week'))
                else:
                    output.append(f'{weeks}w')

        if elem <= 0:
            continue

        if brief:
            output.append(f'{elem}{brief_attr}')
        else:
            output.append(format(plural(elem), attr))

    if accuracy is not None:
        output = output[:accuracy]

    if len(output) == 0:
        return 'now'
    else:
        return (
            ' '.join(output) + suffix
            if brief
            else human_join(output, conj='and') + suffix
        )


def strip_tzinfo(dt: datetime.datetime):
    """Removes tzinfo from a datetime"""
    return dt.replace(tzinfo=None)


def add_tzinfo(dt: datetime.datetime):
    """Adds tzinfo to a datetime.

    The timezone is changed to UTC by default"""
    return dt.replace(tzinfo=datetime.timezone.utc)


def format_timestamp(timestamp, *, timezone="UTC") -> str:
    return timestamp.strftime(f"%Y-%m-%d %H:%M:%S {timezone}")


def get_utc_timestamp(timestamp) -> str:
    return format_timestamp(timestamp)


def format_relative(dt):
    """Returns the discord markdown for a relative timestamp"""
    return format_dt(dt, style="R")
