"""
Unit tests for the heat-based automod system
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock


class MockRecord:
    """Mock asyncpg.Record for testing"""
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)


class TestHeatConfig(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.mock_bot = Mock()
        self.mock_bot.redis_pool = AsyncMock()

        # Create a sample heat config record
        config_record = MockRecord({
            'guild_id': 123456789,
            'enabled': True,
            'decay_seconds': 3600,
            'heat_per_violation': {'message-spam': 2.0, 'invite-spam': 5.0}
        })

        # Create sample threshold records
        threshold_records = [
            MockRecord({
                'id': 1,
                'heat_threshold': 10,
                'punishment_type': 'WARN',
                'punishment_duration': None
            }),
            MockRecord({
                'id': 2,
                'heat_threshold': 20,
                'punishment_type': 'MUTE',
                'punishment_duration': 3600
            }),
            MockRecord({
                'id': 3,
                'heat_threshold': 30,
                'punishment_type': 'KICK',
                'punishment_duration': None
            })
        ]

        # Import here to avoid dependency issues
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from lightning.cogs.automod.models import HeatConfig
        
        self.heat_config = HeatConfig(self.mock_bot, config_record, threshold_records)

    def test_heat_config_initialization(self):
        """Test that HeatConfig initializes correctly"""
        self.assertEqual(self.heat_config.guild_id, 123456789)
        self.assertTrue(self.heat_config.enabled)
        self.assertEqual(self.heat_config.decay_seconds, 3600)
        self.assertEqual(self.heat_config.heat_per_violation['message-spam'], 2.0)
        self.assertEqual(len(self.heat_config.thresholds), 3)

    def test_thresholds_sorted(self):
        """Test that thresholds are sorted by heat level"""
        thresholds = [t.threshold for t in self.heat_config.thresholds]
        self.assertEqual(thresholds, [10, 20, 30])

    async def test_add_heat(self):
        """Test adding heat to a user"""
        # Mock Redis response
        self.mock_bot.redis_pool.pipeline.return_value.execute = AsyncMock(return_value=[15.0, True])
        
        new_heat = await self.heat_config.add_heat(987654321, 'message-spam')
        self.assertEqual(new_heat, 15.0)

    async def test_get_user_heat(self):
        """Test getting user heat"""
        # Mock Redis response
        self.mock_bot.redis_pool.get = AsyncMock(return_value='12.5')
        
        heat = await self.heat_config.get_user_heat(987654321)
        self.assertEqual(heat, 12.5)

    async def test_get_user_heat_no_heat(self):
        """Test getting user heat when user has no heat"""
        # Mock Redis response for no heat
        self.mock_bot.redis_pool.get = AsyncMock(return_value=None)
        
        heat = await self.heat_config.get_user_heat(987654321)
        self.assertEqual(heat, 0.0)

    def test_get_punishment_for_heat(self):
        """Test getting the correct punishment for a heat level"""
        # Test heat below all thresholds
        punishment = self.heat_config.get_punishment_for_heat(5.0)
        self.assertIsNone(punishment)

        # Test heat at first threshold
        punishment = self.heat_config.get_punishment_for_heat(10.0)
        self.assertIsNotNone(punishment)
        self.assertEqual(punishment.punishment, 'WARN')

        # Test heat between thresholds
        punishment = self.heat_config.get_punishment_for_heat(15.0)
        self.assertIsNotNone(punishment)
        self.assertEqual(punishment.punishment, 'WARN')

        # Test heat at second threshold
        punishment = self.heat_config.get_punishment_for_heat(20.0)
        self.assertIsNotNone(punishment)
        self.assertEqual(punishment.punishment, 'MUTE')
        self.assertEqual(punishment.duration, 3600)

        # Test heat above all thresholds
        punishment = self.heat_config.get_punishment_for_heat(50.0)
        self.assertIsNotNone(punishment)
        self.assertEqual(punishment.punishment, 'KICK')

    async def test_reset_heat(self):
        """Test resetting user heat"""
        self.mock_bot.redis_pool.delete = AsyncMock(return_value=1)
        
        await self.heat_config.reset_heat(987654321)
        self.mock_bot.redis_pool.delete.assert_called_once()


if __name__ == '__main__':
    unittest.main()
