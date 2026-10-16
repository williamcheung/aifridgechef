import base64

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from llm import get_llm, invoke_llm_chain_async
from log_util import logger
from time_it import time_it_async
from util import UTF8_ENCODING, load_prompt

async def analyze_image_from_path(image_path: str, prompt_file: str, prompt_vars: dict[str, str] | None = None) -> dict | str:
    with open(image_path, 'rb') as image_file:
        image_data = image_file.read()
    image_format = get_image_format(image_path)
    return await analyze_image_from_bytes(image_data, prompt_file, image_format, prompt_vars=prompt_vars)

@time_it_async
async def analyze_image_from_bytes(image_data: bytes, prompt_file: str, image_format: str, output_parser_type=JsonOutputParser, prompt_vars: dict[str, str] | None = None) -> dict | str:
    img_base64 = base64.b64encode(image_data).decode(UTF8_ENCODING)
    prompt = load_prompt(prompt_file)
    # Substitute {name} placeholders without str.format() so the literal
    # JSON braces in the prompt are left untouched.
    for key, value in (prompt_vars or {}).items():
        prompt = prompt.replace('{' + key + '}', value)
    prompt_template = ChatPromptTemplate.from_messages([
        HumanMessage(
            content=[
                {'type': 'text', 'text': prompt},
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': f'data:image/{image_format.lower()};base64,{img_base64}',
                        'detail': 'high'
                    }
                }
            ]
        ),
    ])

    llm = get_llm()
    chain = prompt_template | llm | output_parser_type()
    response = await invoke_llm_chain_async(chain)
    logger.info(f'{response=}')

    return response

def get_image_format(image_path: str) -> str:
    file_ext = image_path.split('.')[-1].lower()
    match file_ext:
        case 'jpg' | 'jpeg':
            return 'jpeg'
        case 'png' | 'gif' | 'webp':
            return file_ext
        case _:
            raise ValueError(f'Unsupported image format for {image_path=}')

if __name__ == '__main__':
    # test usage
    import asyncio
    import glob
    import json
    import os

    TEST_DATA_DIR = 'test_data'
    image_paths = glob.glob(os.path.join(TEST_DATA_DIR, '*.jpg'))

    async def _test():
        for image_path in image_paths:
            foods: list[dict] = await analyze_image_from_path(image_path, 'get_foods_from_image.prompt.txt', prompt_vars={'language': 'English'})
            file_name = image_path.split(os.path.sep)[-1].split(os.path.extsep)[0]
            with open(f'{TEST_DATA_DIR}{os.path.sep}foods_from_image_{file_name}.json', 'w', encoding=UTF8_ENCODING) as f:
                f.write(json.dumps(foods, indent=2))
            pass

    asyncio.run(_test())
