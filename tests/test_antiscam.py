import unittest
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, module="discord.player")

from lightning.cogs.ext.antiscam import AntiScamResult, ScamType  # noqa: E402


class TestAntiScam(unittest.TestCase):
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
        # 100 - 5 (Mentions everyone) - 20 (Invite Link) - 15 (Emoji) - 5 (Was identified in calculate as mal. term)
        self.assertEqual(r.score, 100 - 5 - 20 - 15 - 5)
