import os
import re
import sys
import unittest

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ['DEBUG'] = '0'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from chef_chat import get_chef_chat_response


INVENTORY = [
    {'food': 'Sausages', 'brand': None, 'quantity': 4},
    {'food': 'Baguettes', 'brand': None, 'quantity': 2},
    {'food': 'Green Peas', 'brand': 'Birds Eye', 'quantity': 1},
    {'food': 'Mushrooms', 'brand': None, 'quantity': 1},
    {'food': 'Bread Rolls', 'brand': None, 'quantity': 3},
    {'food': 'Ground Meat', 'brand': None, 'quantity': 2},
    {'food': 'Salmon Fillet', 'brand': 'Wild Catch', 'quantity': 1},
    {'food': 'Smoked Salmon', 'brand': 'Saga', 'quantity': 1},
    {'food': 'Butter', 'brand': 'President', 'quantity': 1},
    {'food': 'Cheese', 'brand': 'President', 'quantity': 1},
    {'food': 'Yogurt', 'brand': 'Danone', 'quantity': 1},
    {'food': 'Lettuce', 'brand': None, 'quantity': 1},
    {'food': 'Apple pie', 'brand': None, 'quantity': 1},
    {'food': 'Ice cream', 'brand': None, 'quantity': 1},
]

USER_TURNS = [
    'what can i make in 15 mins for lunch',
    '2 sausages are enough',
    "i don't want to use my oven",
    'add a small salad',
    'add a dessert',
    'i want ice cream with the pie',
]


class ChefChatConversationTest(unittest.IsolatedAsyncioTestCase):
    async def test_replays_constraint_following_conversation(self):
        history = [{
            'role': 'assistant',
            'content': "I'm your Fridge Chef. Ask me what to cook, what to use first, or how to substitute an ingredient from your inventory.",
        }]
        responses = []

        for user_turn in USER_TURNS:
            history.append({'role': 'user', 'content': user_turn})
            response = await get_chef_chat_response(INVENTORY, history)
            history.append({'role': 'assistant', 'content': response})
            responses.append(response)

        print('\n--- 8B CHEF CHAT REPLAY ---')
        for message in history:
            print(f"\n{message['role']}: {message['content']}")

        violations = []
        after_two_sausages = '\n'.join(responses[1:]).lower()
        if re.search(r'\b(?:3|4) sausages?\b', after_two_sausages):
            violations.append('The bot did not consistently retain the two-sausage constraint.')

        after_no_oven = responses[2:]
        for turn_number, response in enumerate(after_no_oven, start=3):
            normalized = response.lower()
            if re.search(r'\bpreheat (?:the |an )?oven\b|\bbake (?:for|at|in)\b|\bin (?:the|an) oven\b', normalized):
                violations.append(f'Turn {turn_number} instructs the user to use an oven after the no-oven constraint.')

        if '1 lettuce leaf' in responses[3].lower() or 'one lettuce leaf' in responses[3].lower():
            violations.append('The salad is only one lettuce leaf.')

        for turn_number, response in enumerate(responses, start=1):
            minute_ranges = re.findall(r'(\d+)\s*(?:-|–|to)\s*(\d+)\s*minutes?', response.lower())
            if any(int(end) > 15 for _, end in minute_ranges):
                violations.append(f'Turn {turn_number} suggests an operation longer than the 15-minute meal limit.')

        ice_cream_response = responses[-1].lower()
        if re.search(r'^\s*-\s*1 ice cream\s*(?:\([^\n]*\))?$', ice_cream_response, re.MULTILINE):
            violations.append('The ice-cream quantity is expressed as "1 ice cream" instead of a usable serving amount.')
        if re.search(r'below\s+4\s*°?c|4\s*°?c\s*\(40\s*°?f\)', ice_cream_response):
            violations.append('The ice-cream response uses refrigerator temperature instead of freezer temperature.')

        for turn_number, response in enumerate(responses[3:], start=4):
            normalized = response.lower()
            if 'steps:' not in normalized or re.search(r'follow .*steps (?:above|previously)|as described', normalized):
                violations.append(f'Turn {turn_number} refers backward instead of providing the complete updated recipe.')

        self.assertEqual([], violations, '\n'.join(violations))


if __name__ == '__main__':
    unittest.main()
