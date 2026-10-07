import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

import discord

from lightning.events import (CommandEvent, InfractionEvent,
                              LightningAutoModInfractionEvent, MemberJoinEvent,
                              MemberLeaveEvent, MemberRolesUpdateEvent,
                              MemberScreeningEvent, MemberUpdateEvent,
                              TimedActionExpiredEvent, TimeoutExpiredEvent)
from lightning.models import Action
from lightning.modlogformats import (FormatContext, ModAction, NickChange,
                                     Renderer, RoleChange, get_renderer,
                                     renders)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SETTINGS = ("emoji", "minimal with timestamp", "minimal without timestamp", "embed")


class FakeUser:
    def __init__(self, id=1, name="Light", nick=None):
        self.id = id
        self.name = name
        self.nick = nick
        self.mention = f"<@{id}>"
        self.created_at = NOW
        self.joined_at = NOW
        self.display_avatar = SimpleNamespace(url="https://example.com/avatar.png")

    def __str__(self):
        return self.name


def make_action(**kwargs):
    action = Action(1, "ban", FakeUser(2, "Target"), FakeUser(3, "Mod"), "being rude", **kwargs)
    action.infraction_id = 10
    return action


class TestFormatContext(unittest.TestCase):
    def test_from_setting(self):
        # Only the minimal format cares about timestamps, so the others should always keep the default
        cases = {
            "emoji": ("emoji", True),
            "embed": ("embed", True),
            "minimal with timestamp": ("minimal", True),
            "minimal without timestamp": ("minimal", False),
        }
        for setting, (fmt, with_timestamp) in cases.items():
            with self.subTest(setting=setting):
                ctx = FormatContext.from_setting(setting)
                self.assertEqual(ctx.fmt, fmt)
                self.assertEqual(ctx.with_timestamp, with_timestamp)

    def test_unknown_setting_raises(self):
        with self.assertRaises(ValueError):
            FormatContext.from_setting("definitely not a format")


class TestRegistry(unittest.TestCase):
    def test_every_event_has_a_renderer(self):
        user = FakeUser()
        events = (
            MemberJoinEvent(user), MemberLeaveEvent(user), MemberScreeningEvent(user),
            MemberUpdateEvent(user, user, None), MemberRolesUpdateEvent(user, user, None),
            TimedActionExpiredEvent("ban", user, user, NOW, NOW), make_action(),
            TimeoutExpiredEvent(None, user, user, None, NOW),
            CommandEvent(SimpleNamespace(command=SimpleNamespace(qualified_name="ping"), author=user,
                                         message=SimpleNamespace(created_at=NOW),
                                         channel=SimpleNamespace(id=5, name="general", mention="<#5>")))
        )
        for event in events:
            with self.subTest(event=type(event).__name__):
                self.assertIsInstance(get_renderer(event), Renderer)

    def test_unknown_event_raises(self):
        with self.assertRaises(LookupError):
            get_renderer(object())

    def test_subclass_beats_parent(self):
        # MemberRolesUpdateEvent is a MemberUpdateEvent, but it has its own renderer
        user = FakeUser()
        self.assertIsInstance(get_renderer(MemberUpdateEvent(user, user, None)), NickChange)
        self.assertIsInstance(get_renderer(MemberRolesUpdateEvent(user, user, None)), RoleChange)

    def test_subclass_falls_back_to_parent(self):
        class Child(MemberJoinEvent):
            __slots__ = ()

        self.assertEqual(type(get_renderer(Child(FakeUser()))).__name__, "MemberJoin")

    def test_renders_registers_class(self):
        class Thing:
            pass

        @renders(Thing)
        class ThingRenderer(Renderer[Thing]):
            pass

        self.assertIsInstance(get_renderer(Thing()), ThingRenderer)

    def test_automod_event_uses_action_renderer(self):
        # The cog hands over event.action, so make sure automod events still end up at ModAction
        self.assertTrue(issubclass(LightningAutoModInfractionEvent, InfractionEvent))
        self.assertIsInstance(get_renderer(make_action()), ModAction)


class TestRendering(unittest.TestCase):
    def test_every_format_renders(self):
        user = FakeUser(nick="Old")
        renderers = (
            get_renderer(MemberJoinEvent(user)), get_renderer(MemberLeaveEvent(user)),
            get_renderer(MemberScreeningEvent(user)), get_renderer(MemberUpdateEvent(user, user, None)),
            get_renderer(TimedActionExpiredEvent("ban", user, user, NOW, NOW)), get_renderer(make_action()),
            get_renderer(TimeoutExpiredEvent(None, user, user, None, NOW)),
            get_renderer(TimeoutExpiredEvent(None, user, None, None, NOW))
        )
        for renderer in renderers:
            for setting in SETTINGS:
                with self.subTest(renderer=type(renderer).__name__, setting=setting):
                    result = renderer.render(FormatContext.from_setting(setting))
                    expected = discord.Embed if setting == "embed" else str
                    self.assertIsInstance(result, expected)

    def test_timestamp_only_when_asked(self):
        renderer = get_renderer(MemberLeaveEvent(FakeUser()))
        with_timestamp = renderer.render(FormatContext("minimal", True))
        without_timestamp = renderer.render(FormatContext("minimal", False))
        self.assertTrue(with_timestamp.startswith("["))
        self.assertFalse(without_timestamp.startswith("["))
        self.assertTrue(with_timestamp.endswith(without_timestamp))

    def test_mod_action_mentions(self):
        # The cog decides to only use these for the emoji format, renderers just report who's involved
        action = make_action()
        self.assertEqual(get_renderer(action).mentions(), [action.target, action.moderator])

    def test_timed_action_has_same_fields_in_every_format(self):
        # Used to be a different argument order for the embed format
        user, mod = FakeUser(2, "Target"), FakeUser(3, "Mod")
        renderer = get_renderer(TimedActionExpiredEvent("ban", user, mod, NOW, NOW))
        self.assertIn("Target", renderer.minimal(FormatContext("minimal")))
        embed = renderer.embed()
        self.assertIn("Target", embed.description)
        self.assertIn("Mod", embed.fields[0].value)

    def test_mod_action_requires_logged_infraction(self):
        action = Action(1, "ban", FakeUser(), FakeUser(2), "reason")
        with self.assertRaises(ValueError):
            ModAction(action)

    def test_mod_action_expiry_shows_in_minimal(self):
        renderer = get_renderer(make_action(expiry=NOW))
        self.assertIn("**Expiry**", renderer.minimal(FormatContext("minimal")))


class TestNickChange(unittest.TestCase):
    def render(self, before, after, setting="embed"):
        member = FakeUser(nick=after)
        event = MemberUpdateEvent(FakeUser(nick=before), member, None)
        return get_renderer(event).render(FormatContext.from_setting(setting))

    def test_titles(self):
        cases = {
            ("old", "new"): "Member Nickname Update",
            (None, "new"): "Member Nickname Add",
            ("old", None): "Member Nickname Removed",
        }
        for (before, after), title in cases.items():
            with self.subTest(before=before, after=after):
                self.assertEqual(self.render(before, after).title, title)

    def test_no_nicknames_does_not_raise(self):
        # Neither nickname set used to blow up on a None description
        for setting in SETTINGS:
            with self.subTest(setting=setting):
                self.assertIsNotNone(self.render(None, None, setting))

    def test_moderator_is_shown(self):
        member = FakeUser(nick="new")
        event = MemberUpdateEvent(FakeUser(nick="old"), member, None)
        event.moderator = FakeUser(3, "Mod")
        embed = get_renderer(event).embed()
        self.assertEqual(embed.fields[0].name, "Moderator")


class TestEmojiOutput(unittest.TestCase):
    def test_screening_has_balanced_parentheses(self):
        text = get_renderer(MemberScreeningEvent(FakeUser())).emoji()
        self.assertEqual(text.count("("), text.count(")"))


if __name__ == "__main__":
    unittest.main()
