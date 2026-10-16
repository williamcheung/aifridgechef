from collections import defaultdict
import json

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from typing import TypedDict

from llm import get_llm_lite, invoke_llm_chain_async
from log_util import logger
from util import load_prompt
from vision import analyze_image_from_path

class FoodInventoryItem(TypedDict):
    food: str
    brand: str
    quantity: int

async def get_foods_from_image(image_path: str, language: str = 'English') -> list[FoodInventoryItem]:
    foods: list[FoodInventoryItem] = await analyze_image_from_path(
        image_path, 'get_foods_from_image.prompt.txt', prompt_vars={'language': language}
    )
    foods = _combine_duplicate_food_brand_pairs(foods)
    return foods

async def update_food_inventory(inventory: list[FoodInventoryItem], inventory_update: str, language: str = 'English') -> list[FoodInventoryItem]:
    prompt = load_prompt('update_food_inventory.prompt.txt')
    prompt_template = PromptTemplate.from_template(prompt)
    llm = get_llm_lite()
    chain = prompt_template | llm | JsonOutputParser()
    response = await invoke_llm_chain_async(chain, {
        'inventory': json.dumps(inventory),
        'inventory_update': inventory_update,
        'language': language,
    })
    logger.info(f'{response=}')
    foods: list[FoodInventoryItem] = response['foods']
    return _combine_duplicate_food_brand_pairs(foods)

def _combine_duplicate_food_brand_pairs(foods: list[FoodInventoryItem]) -> list[FoodInventoryItem]:
    # dict to add up quantities of duplicated food items
    # - key: food name/brand pair (tuple)
    # - value: aggregated quantity (int)
    aggregated_quantities: dict[tuple[str, str], int] = defaultdict(int)
    for food in foods:
        pair = (food['food'], _normalize_brand(food['brand']))
        aggregated_quantities[pair] += food['quantity']

    # Always rebuild from the aggregated dict so brand normalization (null/none -> None)
    # is applied even when there were no duplicates to combine.
    return [FoodInventoryItem(food=food, brand=brand, quantity=quantity) for (food, brand), quantity in aggregated_quantities.items()]

def _normalize_brand(brand) -> str | None:
    # The LLM sometimes returns a placeholder string (e.g. 'null', 'none', 'n/a')
    # instead of a real null for an unknown brand. Normalize those to None so the
    # UI does not render "(null)" after the food name.
    if not isinstance(brand, str):
        return brand
    if brand.strip().lower() in ('', 'null', 'none', 'n/a', 'na', 'unknown'):
        return None
    return brand

def combine_food_inventories(food_inventories: list[list[FoodInventoryItem]]) -> list[FoodInventoryItem]:
    if len(food_inventories) == 1:
        return food_inventories[0]

    foods: list[FoodInventoryItem] = []
    for inventory in food_inventories:
        foods.extend(inventory)
    foods = _combine_duplicate_food_brand_pairs(foods)
    return foods

if __name__ == '__main__':
    import json

    from util import UTF8_ENCODING

    food_inventory_file = 'test_data/foods_from_image_pantry_GettyImages-493239254-b4ee2820e10a4230a747154c88366f86_SONARPRO.json'
    with open(food_inventory_file, encoding=UTF8_ENCODING) as f:
        foods: list[dict[str, str|int]] = json.load(f)

    foods = _combine_duplicate_food_brand_pairs(foods)

    food_inventory_file_deduped = food_inventory_file.replace('.json', '_deduped.json', 1)
    with open(food_inventory_file_deduped, 'w', encoding=UTF8_ENCODING) as f:
        f.write(json.dumps(foods, indent=2))

    foods_doubled = combine_food_inventories([foods, foods])
    food_inventory_file_doubled = food_inventory_file.replace('.json', '_doubled.json', 1)
    with open(food_inventory_file_doubled, 'w', encoding=UTF8_ENCODING) as f:
        f.write(json.dumps(foods_doubled, indent=2))

    pass
