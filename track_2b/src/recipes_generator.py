from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from typing import Any

from log_util import logger
from llm import get_llm, invoke_llm_chain_async
from util import load_prompt

async def get_recipes(meal: str, foods: str, dietary_restrictions: list[str], medical_diagnoses: list[str], cuisine_types: list[str], serves: list[str], recipes_to_exclude: list[str] = [], language: str = 'English') -> list[dict[str, Any]]:
    prompt = load_prompt('get_recipes_from_foods.prompt.txt')
    prompt_template = PromptTemplate.from_template(prompt)
    llm = get_llm()
    chain = prompt_template | llm | JsonOutputParser()
    response = await invoke_llm_chain_async(chain, {
        'meal': meal,
        'foods': foods,
        'dietary_restrictions': dietary_restrictions,
        'medical_diagnoses': medical_diagnoses,
        'cuisine_types': cuisine_types,
        'serves': serves,
        'recipes_to_exclude': recipes_to_exclude,
        'language': language,
    })
    logger.info(f'{response=}')
    recipes: list[dict[str, Any]] = response['recipes']
    for recipe in recipes:
        c, f, p = recipe['carbohydrate_percent'], recipe['fat_percent'], recipe['protein_percent']
        total = c + f + p
        if total != 100:
            recipe['carbohydrate_percent'] = round(c * 100 / total)
            recipe['fat_percent'] = round(f * 100 / total)
            recipe['protein_percent'] = 100 - recipe['carbohydrate_percent'] - recipe['fat_percent']
    return recipes
