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


class ChefChatGermanLanguageTest(unittest.IsolatedAsyncioTestCase):
    async def test_german_recipe_translates_all_structure_labels(self):
        history = [
            {
                'role': 'assistant',
                'content': "I'm your Fridge Chef. Ask me what to cook, what to use first, or how to substitute an ingredient from your inventory.",
            },
            {'role': 'user', 'content': 'Machen Sie ein Frühstück'},
        ]

        response = await get_chef_chat_response(INVENTORY, history)
        print(f'\n--- GERMAN CHEF CHAT RESPONSE ---\n\n{response}')

        self.assertNotIn('<|inner_suffix|>', response)
        for english_label in ('Recipe', 'Total time', 'Ingredients', 'Instructions', 'Food-safety note'):
            self.assertIsNone(
                re.search(rf'(?im)^\s*[*#-]*\s*{re.escape(english_label)}\s*:', response),
                f'English recipe label remained in the German response: {english_label}',
            )

        normalized = response.lower()
        expected_german_labels = {
            'recipe': ('rezept',),
            'total time': ('gesamtzeit', 'gesamtdauer', 'zubereitungszeit'),
            'ingredients': ('zutaten',),
            'instructions': ('anleitung', 'zubereitung'),
        }
        for meaning, translations in expected_german_labels.items():
            self.assertTrue(
                any(translation in normalized for translation in translations),
                f'No German label for {meaning!r} was found. Expected one of: {translations}',
            )


if __name__ == '__main__':
    unittest.main()
