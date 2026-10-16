import os
import re
import unittest

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ['DEBUG'] = '0'

from chef_chat import get_chef_chat_response


INVENTORY = [
    {'food': 'Pancake', 'brand': None, 'quantity': 1},
    {'food': 'Strawberries', 'brand': None, 'quantity': 12},
    {'food': 'Butter', 'brand': None, 'quantity': 1},
]


class ChefChatLanguageTest(unittest.IsolatedAsyncioTestCase):
    async def test_french_recipe_translates_all_structure_labels(self):
        history = [
            {
                'role': 'assistant',
                'content': "I'm your Fridge Chef. Ask me what to cook, what to use first, or how to substitute an ingredient from your inventory.",
            },
            {'role': 'user', 'content': 'faites un petit dejeuner'},
        ]

        response = await get_chef_chat_response(INVENTORY, history)
        print(f'\n--- FRENCH CHEF CHAT RESPONSE ---\n\n{response}')

        self.assertNotIn('<|inner_suffix|>', response)
        # "Instructions" is spelled the same in French and English, so it cannot
        # distinguish a translated French response from an English heading.
        for english_label in ('Recipe', 'Total time', 'Ingredients', 'Food-safety note'):
            self.assertIsNone(
                re.search(rf'(?im)^\s*[*#-]*\s*{re.escape(english_label)}\s*:', response),
                f'English recipe label remained in the French response: {english_label}',
            )

        normalized = response.lower()
        for french_label in ('recette', 'temps total', 'ingrédients', 'instructions'):
            self.assertIn(french_label, normalized)


if __name__ == '__main__':
    unittest.main()
