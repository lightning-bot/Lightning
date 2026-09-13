import unittest
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, module="discord.player")

from lightning.cogs.ext.antiscam import AntiScamResult, ScamType  # noqa: E402


class TestAntiScam(unittest.TestCase):
    def test_gardening_message_is_not_a_steam_scam(self):
        # Synthetic example preserving "gift", Unicode punctuation, and no links.
        message = """The tomato seedlings were a lovely gift from my neighbor!
I’m putting them on the balcony — they’re getting plenty of morning sun.
They’ve grown quickly, but I don’t know whether they’re ready for bigger pots.

• Should I move them now, or wait until next weekend?
• There’s a little yellowing on one leaf — is that normal?

I haven’t grown vegetables before, so I’d appreciate any tips.
Our café’s gardener suggested compost, but I’m unsure how much to use."""
        result = AntiScamResult(message).calculate()
        self.assertEqual(result.type, ScamType.UNKNOWN)
        self.assertEqual(result.score, 100)
        # Even all account/context penalties (5 + 8 + 15) stay above timeout.
        self.assertGreaterEqual(result.score - 28, 60)

    def test_unicode_does_not_reduce_steam_score(self):
        plain = AntiScamResult("Steam is great - it's fun!").calculate()
        unicode = AntiScamResult("Steam is great — it’s fun! café 日本語 🎮").calculate()
        self.assertEqual(unicode.score, plain.score)

    def test_repeated_gift_does_not_stack_message_penalties(self):
        single = AntiScamResult("gift [claim](https://example.com)").calculate()
        repeated = AntiScamResult("gift gift gift [claim](https://example.com)").calculate()
        self.assertEqual(single.type, ScamType.STEAM)
        self.assertEqual(repeated.score, single.score)

    def test_steam_phishing_still_triggers(self):
        for message in (
            "50$ for Steam - [steamcommunity.com/gift/7441553](https://test.cloud/1234)",
            "50$ Gift - [steamcommunity.com/gift/69](https://test.cloud/1234)",
            "50$ gift - [steamcommunity.com/gift/832083](https://google.com)\n@everyone @here",
            "catch 50$ - [steamcommunity.com/gift](https://google.com)",
        ):
            with self.subTest(message=message):
                result = AntiScamResult(message).calculate()
                self.assertEqual(result.type, ScamType.STEAM)
                self.assertLess(result.score, 60)

    def test_generic_message(self):
        result = AntiScamResult("Hello, World!")
        r = result.calculate()
        self.assertEqual(r.type, ScamType.UNKNOWN)
        self.assertEqual(len(result.discord_invites), 0)

    def test_invite_drops_without_author(self):
        result = AntiScamResult("https://discord.gg/SpFjsy3 @everyone")
        self.assertIn("https://discord.gg/SpFjsy3", result.discord_invites)
        r = result.calculate_with_invites({"https://discord.gg/SpFjsy3": "Best New 🥵 Server"})
        self.assertEqual(r.type, ScamType.MALICIOUS_NSFW_SERVER)
        # Breaking this down for future reference
        # 100
        # - 5 (Mentions everyone)
        # - 20 (Invite Link)
        # - 5 (Suspect emoji)
        # - 5 (Emoji count)
        # - 5 (Was identified in calculate as mal. term)
        self.assertEqual(r.score, 100 - 5 - 20 - 5 - 5 - 5)
