import os
from pathlib import Path
import unittest

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ['DEBUG'] = '0'

from food_inventory import get_foods_from_image


COIN_IMAGE_PATH = Path(__file__).parent / 'test_data' / 'CCI20240913_0001.jpg'


class FoodDetectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_coin_is_not_detected_as_food(self):
        foods = await get_foods_from_image(str(COIN_IMAGE_PATH))

        self.assertEqual([], foods)


if __name__ == '__main__':
    unittest.main()
