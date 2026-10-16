import os

from dotenv import load_dotenv
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from openai import InternalServerError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, stop_after_delay, wait_exponential

from time_it import time_it, time_it_async

load_dotenv()

MODEL = os.getenv('APERTUS_MODEL')
MODEL_LITE = os.getenv('APERTUS_MODEL_LITE')
MODEL_THINKING = os.getenv('APERTUS_MODEL_THINKING')

BASE_URL = os.getenv('APERTUS_BASE_URL')
API_KEY = os.getenv('APERTUS_API_KEY')

MAX_TOKENS = int(os.getenv('MAX_TOKENS'))
MAX_TOKENS_THINKING = int(os.getenv('MAX_TOKENS_THINKING', str(100_000)))
RPM = int(os.getenv('RPM'))
TEMPERATURE = int(os.getenv('TEMPERATURE', 0))
APERTUS_FINAL_ANSWER_DELIMITER = '<|inner_suffix|>'

from log_util import logger

def _get_llm(model, max_tokens=None):
    return ChatOpenAI(model=model, base_url=BASE_URL, api_key=API_KEY, max_tokens=max_tokens or MAX_TOKENS, temperature=TEMPERATURE, max_retries=0) # disable LangChain max_retries to use Tenacity

def get_llm():
    return _get_llm(MODEL)

def get_llm_lite():
    return _get_llm(MODEL_LITE)

def get_llm_thinking():
    # Reasoning model, used for tasks that need multi-step reasoning (e.g. the
    # chat summary's grouping of recipe variations). Given a larger token budget
    # than the instruct models because the reasoning trace plus the final answer
    # need more headroom (the regular MAX_TOKENS would risk truncating the answer).
    return _get_llm(MODEL_THINKING, max_tokens=MAX_TOKENS_THINKING)

@time_it
def invoke_llm(llm, input: LanguageModelInput):
    try:
        rsp = _invoke_with_retry(llm, input)
        return rsp
    except Exception:
        raise
    finally:
        _log_model(llm)

@time_it_async
async def invoke_llm_chain_async(chain, input: dict | None = {}):
    try:
        rsp = await _ainvoke_llm_chain_with_retry(chain, input)
        return _clean_llm_chain_response(rsp)
    except Exception:
        raise
    finally:
        llm = next(iter([step for step in chain.steps if isinstance(step, BaseChatModel)]), None)
        if llm:
            _log_model(llm)
        else:
            logger.warning('--- No model found in chain')

def _log_model(llm):
    logger.info(f'--- Model used: {llm.model_name}')


def _clean_llm_chain_response(response):
    if isinstance(response, str):
        return response.rsplit(APERTUS_FINAL_ANSWER_DELIMITER, 1)[-1].strip()
    return response

# retry constants
WAIT_MIN_BUFFER_FACTOR = float(os.getenv('WAIT_MIN_BUFFER_FACTOR', '1.1'))
WAIT_MAX_SECONDS = float(os.getenv('WAIT_MAX_SECONDS', '4'))
STOP_AFTER_ATTEMPT_COUNT = int(os.getenv('STOP_AFTER_ATTEMPT_COUNT', '3'))
STOP_AFTER_DELAY_SECONDS = float(os.getenv('STOP_AFTER_DELAY_SECONDS', '15'))
MIN_WAIT_FLOOR_SECONDS = float(os.getenv('MIN_WAIT_FLOOR_SECONDS', '0.1'))

SECONDS_PER_REQUEST = 60 / RPM
WAIT_MIN_SECONDS = max(SECONDS_PER_REQUEST * WAIT_MIN_BUFFER_FACTOR, MIN_WAIT_FLOOR_SECONDS)

apply_rate_limit_retry = retry(
    wait=wait_exponential(
        min=WAIT_MIN_SECONDS,
        max=WAIT_MAX_SECONDS
    ),
    stop=(
        stop_after_attempt(STOP_AFTER_ATTEMPT_COUNT) |
        stop_after_delay(STOP_AFTER_DELAY_SECONDS)
    ),
    retry=retry_if_exception_type((RateLimitError, InternalServerError)),
    before_sleep=lambda retry_state: logger.info(
        f'Transient LLM error. Retrying in {retry_state.next_action.sleep:.2f} seconds... (Attempt {retry_state.attempt_number})'
    )
)

@apply_rate_limit_retry
def _invoke_with_retry(llm: ChatOpenAI, input: LanguageModelInput):
    return llm.invoke(input)

@apply_rate_limit_retry
async def _ainvoke_llm_chain_with_retry(chain, input):
    return await chain.ainvoke(input)
