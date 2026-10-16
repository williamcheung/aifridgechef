import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from food_inventory import FoodInventoryItem
from llm import get_llm, get_llm_thinking, invoke_llm_chain_async
from util import load_prompt


MAX_CHAT_MESSAGES = 30


async def get_chef_chat_response(
    inventory: list[FoodInventoryItem],
    chat_history: list[dict[str, str]],
) -> str:
    """Answer the latest user message using the current food inventory."""
    if not inventory:
        raise ValueError('The chef chat requires at least one inventory item.')

    messages = _get_recent_chat_messages(chat_history)
    if not messages or messages[-1]['role'] != 'user':
        raise ValueError('The chef chat requires a user message.')

    prompt = ChatPromptTemplate.from_messages([
        ('system', load_prompt('chef_chat.prompt.txt')),
        MessagesPlaceholder(variable_name='chat_history'),
    ])
    chain = prompt | get_llm() | StrOutputParser()
    response = await invoke_llm_chain_async(chain, {
        'inventory': json.dumps(inventory, ensure_ascii=False),
        'chat_history': messages,
    })
    return response.strip()


def _get_recent_chat_messages(chat_history: list[dict]) -> list[dict[str, str]]:
    messages = []
    for message in chat_history:
        role = message.get('role')
        content = _get_text_content(message.get('content'))
        if role in {'user', 'assistant'} and content:
            messages.append({'role': role, 'content': content})
    messages = messages[-MAX_CHAT_MESSAGES:]
    # prevent truncated history from beginning with an orphaned assistant response
    while messages and messages[0]['role'] == 'assistant':
        messages.pop(0)
    return messages


def _get_text_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = [
            block.get('text', '')
            for block in content
            if isinstance(block, dict) and block.get('type') == 'text'
        ]
        return '\n'.join(text_parts).strip()
    return ''


async def get_chat_summary(chat_history: list[dict[str, str]]) -> str:
    """Summarize the conversation into Markdown (for the downloadable summary).

    Collapses repeated tweaks of the same recipe to its final version, keeps
    distinct recipes, and writes in the language the user used most recently.
    This is an expensive LLM call and is only invoked on demand (button click).
    """
    messages = _get_recent_chat_messages(chat_history)
    if not any(message['role'] == 'user' for message in messages):
        raise ValueError('The chat summary requires at least one user message.')

    transcript = _format_chat_transcript(messages)
    # Substitute via replace (not str.format) so any braces in the chat text are
    # left untouched.
    prompt_text = load_prompt('summarize_chat.prompt.txt').replace('{chat_history}', transcript)

    prompt = ChatPromptTemplate.from_messages([('human', '{prompt_text}')])
    # Use the reasoning model: grouping recipe variations and keeping only the
    # final version of each is a multi-step reasoning task the instruct model
    # does not reliably perform.
    chain = prompt | get_llm_thinking() | StrOutputParser()
    response = await invoke_llm_chain_async(chain, {'prompt_text': prompt_text})
    return response.strip()


def _format_chat_transcript(messages: list[dict[str, str]]) -> str:
    role_labels = {'user': 'User', 'assistant': 'Assistant'}
    lines = []
    for message in messages:
        role = role_labels.get(message['role'], message['role'])
        lines.append(f'{role}: {message["content"]}')
    return '\n\n'.join(lines)
