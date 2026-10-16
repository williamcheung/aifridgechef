import base64
import json
import mimetypes

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate

from audio_transcription import _has_audible_signal
from food_inventory import FoodInventoryItem
from llm import get_llm_lite, invoke_llm_chain_async
from log_util import logger
from util import UTF8_ENCODING, load_prompt

NO_UPDATE_RESPONSE = '[NO_UPDATE]'

async def get_inventory_update_from_audio(audio_file_path: str, inventory: list[FoodInventoryItem]) -> str:
    if not _has_audible_signal(audio_file_path):
        logger.info('No audible speech signal detected; skipping inventory update interpretation.')
        return ''

    with open(audio_file_path, 'rb') as audio_file:
        audio_base64 = base64.b64encode(audio_file.read()).decode(UTF8_ENCODING)

    audio_mime_type = mimetypes.guess_type(audio_file_path)[0] or 'audio/wav'
    prompt = PromptTemplate.from_template(load_prompt('get_inventory_update_from_audio.prompt.txt')).format(
        inventory=json.dumps(inventory)
    )
    prompt_template = ChatPromptTemplate.from_messages([
        HumanMessage(
            content=[
                {'type': 'text', 'text': prompt},
                {
                    'type': 'audio_url',
                    'audio_url': {
                        'url': f'data:{audio_mime_type};base64,{audio_base64}'
                    }
                }
            ]
        )
    ])

    llm = get_llm_lite()
    chain = prompt_template | llm | StrOutputParser()
    proposed_update = (await invoke_llm_chain_async(chain)).strip().strip('"')
    logger.info(f'{proposed_update=}')

    normalized_update = proposed_update.casefold()
    invalid_response_fragments = (
        NO_UPDATE_RESPONSE.casefold(),
        "don't have the audio",
        'do not have the audio',
        'please provide the audio',
        'return only the proposed inventory update',
    )
    if any(fragment in normalized_update for fragment in invalid_response_fragments):
        logger.info('Apertus returned no usable inventory update.')
        return ''

    return proposed_update
