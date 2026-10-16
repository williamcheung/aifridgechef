import base64
import math
import mimetypes
import wave

from array import array

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from llm import get_llm, invoke_llm_chain_async
from log_util import logger
from util import UTF8_ENCODING, load_prompt

MIN_NORMALIZED_RMS = 0.01
NO_SPEECH_RESPONSE = '[NO_SPEECH]'

async def transcribe_audio(audio_file_path: str) -> str:
    if not _has_audible_signal(audio_file_path):
        logger.info('No audible speech signal detected; skipping transcription.')
        return ''

    with open(audio_file_path, 'rb') as audio_file:
        audio_base64 = base64.b64encode(audio_file.read()).decode(UTF8_ENCODING)

    audio_mime_type = mimetypes.guess_type(audio_file_path)[0] or 'audio/wav'
    prompt = load_prompt('transcribe_audio.prompt.txt')
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

    llm = get_llm()
    chain = prompt_template | llm | StrOutputParser()
    transcription = (await invoke_llm_chain_async(chain)).strip()
    logger.info(f'{transcription=}')

    normalized_transcription = transcription.casefold()
    invalid_response_fragments = (
        NO_SPEECH_RESPONSE.casefold(),
        "don't have the audio",
        'do not have the audio',
        'please provide the spoken words',
        'the speaker is describing a natural-language update',
        'return only the transcription as plain text',
    )
    if any(fragment in normalized_transcription for fragment in invalid_response_fragments):
        logger.info('Apertus returned no usable transcription.')
        return ''

    return transcription

def _has_audible_signal(audio_file_path: str) -> bool:
    try:
        with wave.open(audio_file_path, 'rb') as audio_file:
            sample_width = audio_file.getsampwidth()
            sample_type = {1: 'B', 2: 'h', 4: 'i'}.get(sample_width)
            if not sample_type:
                return True

            samples = array(sample_type, audio_file.readframes(audio_file.getnframes()))
            if not samples:
                return False

            if sample_width == 1:
                centered_samples = (sample - 128 for sample in samples)
                max_amplitude = 128
            else:
                centered_samples = iter(samples)
                max_amplitude = 1 << (sample_width * 8 - 1)

            rms = math.sqrt(math.fsum(sample * sample for sample in centered_samples) / len(samples))
            normalized_rms = rms / max_amplitude
            logger.info(f'Audio {normalized_rms=:.4f}')
            return normalized_rms >= MIN_NORMALIZED_RMS
    except (wave.Error, EOFError):
        # Let Apertus handle formats other than PCM WAV.
        return True
