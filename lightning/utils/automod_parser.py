from enum import IntEnum
from typing import Literal, Optional

import discord
from pydantic import BaseModel, validator
from tomlkit import loads as toml_loads
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument


class ConfigurationError(Exception):
    ...


class AutomodPunishmentEnum(IntEnum):
    DELETE = 1
    WARN = 2
    MUTE = 3
    KICK = 4
    BAN = 5


def convert_to_automod_punishment(value: str):
    try:
        return AutomodPunishmentEnum(value)
    except Exception:
        raise ConfigurationError("Invalid automod punishment supplied")


class AutomodPunishmentModel(BaseModel):
    type: AutomodPunishmentEnum
    seconds: Optional[float]


class BaseTableModel(BaseModel):
    type: Literal["message-spam", "mass-mentions"]
    count: int
    punishment: AutomodPunishmentModel


class MessageSpamModel(BaseTableModel):
    seconds: float

    @validator('punishment')
    def validate_punishment(cls, value):
        if value.type is AutomodPunishmentEnum.DELETE:
            raise ConfigurationError("DELETE punishment is not a valid type")
        return value


def parse_config(key: str, value):
    # Other configuration parameters may need to be validated...

    punishment = value.get("punishment", None)

    if punishment and type(punishment) is not Table:  # at some point we'll support String
        # Optional link to configuration docs
        raise ConfigurationError("Punishment should be a subtable.")

    if key == "mass-mentions":
        return BaseTableModel(type=key, **value)

    try:
        return MessageSpamModel(type=key, **value)
    except Exception as e:
        raise ConfigurationError(e)


def read_file(file: TOMLDocument):
    cfgs = []
    for key, value in list(file.items()):
        if key == "automod":
            if type(value) != Table:
                raise ConfigurationError(f"Expected a subtable, got {value.__class__.__name__} instead.")

            for key, value in list(value.items()):
                cfgs.append(parse_config(key, value))
    return cfgs


async def from_attachment(file: discord.Attachment):
    file = await file.read()
    x = toml_loads(file)
    return read_file(x)
