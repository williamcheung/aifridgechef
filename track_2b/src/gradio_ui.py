import base64
import gradio as gr
import time

from typing import Any

from bs4 import BeautifulSoup
from enum import Enum
from jinja2 import Environment, FileSystemLoader
from markdown_it import MarkdownIt

from audio_transcription import transcribe_audio
from chef_chat import get_chef_chat_response, get_chat_summary
from food_inventory import FoodInventoryItem, combine_food_inventories, get_foods_from_image, update_food_inventory
from log_util import logger
from recipes_generator import get_recipes
from settings import USER_DATA_DIR
from translations import get_labels
from util import UTF8_ENCODING, yield_lines_from_file

BRAND = 'AI Fridge'
TITLE = f'{BRAND} Chef'
INVENTORY_LIST_DESC = 'Food Inventory List'
MARKDOWN_HEADER = f'#####'
INVENTORY_LIST_TITLE = f'{MARKDOWN_HEADER} {INVENTORY_LIST_DESC}'
RECIPE_BOOK_TITLE = f'{BRAND} Recipe Book'
CHAT_SUMMARY_TITLE_TEXT = f'{BRAND} Chat Summary'
FRUITICONS = '🍇🍌🍒'
CHAT_SUMMARY_TITLE = f'{CHAT_SUMMARY_TITLE_TEXT}{FRUITICONS}'

# Single source of truth for the Swiss flag artwork. Read once at startup and
# reused as inline SVG (footer link) and as a base64 data-URI (dropdown CSS
# background), so the flag is defined in exactly one place: images/swiss_flag.svg.
def _load_swiss_flag():
    with open('images/swiss_flag.svg', 'r', encoding=UTF8_ENCODING) as f:
        raw = f.read()
    b64 = base64.b64encode(raw.encode(UTF8_ENCODING)).decode(UTF8_ENCODING)
    # Inline form: drop the XML declaration, collapse whitespace to one line, and
    # tag it with the class the footer CSS sizes (.swiss-flag-inline).
    inline = raw.split('?>', 1)[-1].strip()
    inline = ' '.join(inline.split())
    inline = inline.replace('<svg ', '<svg class="swiss-flag-inline" ', 1)
    return inline, b64

SWISS_FLAG_SVG_INLINE, SWISS_FLAG_SVG_B64 = _load_swiss_flag()

env = Environment(loader=FileSystemLoader('templates'))
inventory_template = env.get_template('food_inventory.md')
recipes_template = env.get_template('recipes.html')
combined_recipes_template = env.get_template('recipes_combined.html')
chat_summary_template = env.get_template('chat_summary.html')

_markdown = MarkdownIt('commonmark', {'breaks': True, 'linkify': True})

# Shared "order up!" kitchen counter bell, played via the Web Audio API (no audio
# asset or visible player needed). Used when a long-running task finishes (recipe
# generation and chat-summary download) to call the user back to the screen.
# Browser autoplay is allowed because a user click triggered the task.
RING_KITCHEN_BELL_JS_BODY = '''
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx();
        // Two quick bright metallic dings, like a restaurant pass bell.
        const ding = (startTime) => {
            // A few inharmonic high partials with fast decay give a bell timbre.
            [1, 2.7, 4.2].forEach((mult, i) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.value = 1050 * mult;
                const peak = 0.5 / (i + 1);
                gain.gain.setValueAtTime(0.0001, startTime);
                gain.gain.exponentialRampToValueAtTime(peak, startTime + 0.004);
                gain.gain.exponentialRampToValueAtTime(0.0001, startTime + 0.9);
                osc.connect(gain).connect(ctx.destination);
                osc.start(startTime);
                osc.stop(startTime + 0.95);
            });
        };
        const now = ctx.currentTime;
        ding(now);
        ding(now + 0.18);
        // Close well after the second ding has fully decayed (it ends ~1.13s in);
        // a generous margin prevents the tail being cut when audio scheduling is
        // delayed (e.g. right after triggering the summary download).
        setTimeout(() => ctx.close(), 2500);
    } catch (e) { /* audio not available; ignore */ }
'''

FRIDGE_CHEF_GREETING = "I'm your Fridge Chef. Ask me what to cook, what to use first, or how to substitute an ingredient from your inventory."
FRIDGE_CHEF_DISABLED_GREETING = 'Add food to your inventory to start chatting with your Fridge Chef.'

class MealType(Enum):
    BREAKFAST = 'Breakfast'
    LUNCH = 'Lunch'
    DINNER = 'Dinner'

def get_fridge_chef_ui_state(inventory_state: list[FoodInventoryItem], chat_history: list[dict[str, str]], chat_busy: bool = False, inventory_busy: bool = False) \
    -> tuple[list[dict[str, str]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    ''' returns: chat_history, chat_message_update, chat_voice_update, chat_disabled_record_update '''
    if inventory_state and not chat_busy and not inventory_busy:
        return chat_history, gr.update(interactive=True), gr.update(visible=True, interactive=True), gr.update(visible=False)

    return (
        chat_history,
        gr.update(interactive=False),
        gr.update(value=None, visible=False, interactive=False),
        gr.update(visible=True)
    )

def get_fridge_chef_control_updates(inventory_state: list[FoodInventoryItem], chat_busy: bool, inventory_busy: bool):
    _, chat_message_update, chat_voice_update, chat_disabled_record_update = get_fridge_chef_ui_state(inventory_state, [], chat_busy, inventory_busy)
    return chat_message_update, chat_voice_update, chat_disabled_record_update

def get_recipe_button_updates(inventory_busy: bool):
    return tuple(gr.update(interactive=not inventory_busy) for _ in MealType)

def get_chat_summary_button_update(chat_history: list[dict[str, str]]):
    # Enable the chat-summary download only once the user has actually chatted
    # (i.e. the history contains a user message, not just the assistant greeting).
    has_user_message = any(message.get('role') == 'user' for message in chat_history)
    return gr.update(interactive=has_user_message)

def get_fridge_chef_greeting_updates(inventory_state: list[FoodInventoryItem], chat_history: list[dict[str, str]]):
    if not any(message['role'] == 'user' for message in chat_history):
        greeting = FRIDGE_CHEF_GREETING if inventory_state else FRIDGE_CHEF_DISABLED_GREETING
        greeting_history = [{'role': 'assistant', 'content': greeting}]
        return greeting_history, greeting_history
    return gr.skip(), gr.skip()

async def process_image(file, inventory_state: list[FoodInventoryItem], inventory_content: str, chat_history: list[dict[str, str]], chat_busy: bool, recipe_language: str = 'English'):
    if not file:
        chat_history, chat_message_update, chat_voice_update, chat_disabled_record_update = get_fridge_chef_ui_state(inventory_state, chat_history, chat_busy)
        yield None, None, inventory_state, inventory_content, gr.update(value='', visible=False), chat_message_update, chat_voice_update, chat_disabled_record_update, False
        return

    image_path = file.name
    yield (
        gr.update(),
        image_path,
        inventory_state,
        inventory_content,
        gr.update(value=f'{MARKDOWN_HEADER} Updating {INVENTORY_LIST_DESC}...⏱️', visible=True),
        gr.update(interactive=False),
        gr.update(value=None, visible=False, interactive=False),
        gr.update(visible=True),
        True
    )

    try:
        items = await get_foods_from_image(image_path, language=recipe_language)
        if not items:
            gr.Warning("No food items were found in this image. Please upload another photo showing food.")
            yield None, None, inventory_state, inventory_content, gr.update(value='', visible=False), gr.update(), gr.update(), gr.update(), False
            return

        inventory_state = combine_food_inventories([inventory_state, items])
        markdown = inventory_template.render(items=inventory_state)
        chat_history, chat_message_update, chat_voice_update, chat_disabled_record_update = get_fridge_chef_ui_state(inventory_state, chat_history, chat_busy)
        yield None, image_path, inventory_state, f'{INVENTORY_LIST_TITLE}\n{markdown}', gr.update(value='', visible=False), gr.update(), gr.update(), gr.update(), False

    except Exception as e:
        chat_history, chat_message_update, chat_voice_update, chat_disabled_record_update = get_fridge_chef_ui_state(inventory_state, chat_history, chat_busy)
        yield None, None, inventory_state, inventory_content, gr.update(value='', visible=False), gr.update(), gr.update(), gr.update(), False
        error_msg = str(e).lower()
        if 'error' in error_msg and 'no food' in error_msg:
            user_msg = "This image doesn't contain food items."
        else:
            user_msg = "Sorry, this image can't be processed."
        user_msg += ' Make sure to choose an image showing food items.'
        gr.Warning(user_msg)

async def update_foods_in_inventory(inventory_update: str, inventory_state: list[FoodInventoryItem], inventory_content: str, chat_history: list[dict[str, str]], chat_busy: bool, recipe_language: str = 'English'):
    if not inventory_update.strip():
        chat_history, chat_message_update, chat_voice_update, chat_disabled_record_update = get_fridge_chef_ui_state(inventory_state, chat_history, chat_busy)
        yield inventory_state, inventory_content, '', gr.update(value='', visible=False), chat_message_update, chat_voice_update, chat_disabled_record_update, False
        return

    yield (
        inventory_state,
        inventory_content,
        inventory_update,
        gr.update(value=f'{MARKDOWN_HEADER} Updating {INVENTORY_LIST_DESC}...⏱️', visible=True),
        gr.update(interactive=False),
        gr.update(value=None, visible=False, interactive=False),
        gr.update(visible=True),
        True
    )

    try:
        inventory_state = await update_food_inventory(inventory_state, inventory_update, language=recipe_language)
        markdown = inventory_template.render(items=inventory_state)
        chat_history, chat_message_update, chat_voice_update, chat_disabled_record_update = get_fridge_chef_ui_state(inventory_state, chat_history, chat_busy)
        yield inventory_state, f'{INVENTORY_LIST_TITLE}\n{markdown}', '', gr.update(value='', visible=False), gr.update(), gr.update(), gr.update(), False
    except Exception as e:
        logger.error(e)
        gr.Warning("Sorry, the inventory couldn't be updated. Please try rephrasing your request.")
        chat_history, chat_message_update, chat_voice_update, chat_disabled_record_update = get_fridge_chef_ui_state(inventory_state, chat_history, chat_busy)
        yield inventory_state, inventory_content, inventory_update, gr.update(value='', visible=False), gr.update(), gr.update(), gr.update(), False

async def append_audio_transcription(audio_file_path: str, text: str):
    if not audio_file_path:
        return text, None

    try:
        transcription = await transcribe_audio(audio_file_path)
        if not transcription:
            gr.Warning("Sorry, I couldn't understand the audio. Please try again or type instead.")
            return text, None
        text = text.rstrip()
        if text:
            text += '\n'
        return text + transcription.strip(), None
    except Exception as e:
        logger.error(e)
        gr.Warning("Sorry, I couldn't understand the audio. Please try again or type instead.")
        return text, None

async def submit_fridge_chef_message(
    message: str,
    inventory_state: list[FoodInventoryItem],
    history: list[dict[str, str]],
):
    message = message.strip()
    if not message:
        yield history, history, '', gr.update(), gr.update(), False
        return

    original_history = history
    history = history + [{'role': 'user', 'content': message}]

    thinking_history = history + [{'role': 'assistant', 'content': '_Thinking…_'}]
    yield (
        thinking_history,
        thinking_history,
        gr.update(value='', interactive=False),
        gr.update(value=None, visible=False, interactive=False),
        gr.update(visible=True),
        True
    )

    try:
        response = await get_chef_chat_response(inventory_state, history)
        response_history = history + [{'role': 'assistant', 'content': response}]
        yield (
            response_history,
            response_history,
            gr.update(value=''),
            gr.update(),
            gr.update(),
            False
        )
    except Exception as e:
        logger.error(e)
        gr.Warning("Sorry, your Fridge Chef couldn't answer. Please try again.")
        yield (
            original_history,
            original_history,
            gr.update(value=message),
            gr.update(),
            gr.update(),
            False
        )

def clear_inventory(chat_history: list[dict[str, str]], chat_busy: bool):
    chat_history, chat_message_update, chat_voice_update, chat_disabled_record_update = get_fridge_chef_ui_state([], chat_history, chat_busy)
    return [], INVENTORY_LIST_TITLE, '', gr.update(value='', visible=False), chat_message_update, chat_voice_update, chat_disabled_record_update, False

def clear_fridge_chef_chat(inventory_state: list[FoodInventoryItem]):
    greeting = FRIDGE_CHEF_GREETING if inventory_state else FRIDGE_CHEF_DISABLED_GREETING
    chat_history = [{'role': 'assistant', 'content': greeting}]
    _, chat_message_update, chat_voice_update, chat_disabled_record_update = get_fridge_chef_ui_state(inventory_state, chat_history)
    return chat_history, chat_history, False, chat_message_update, chat_voice_update, chat_disabled_record_update

async def gen_recipes_for_meal(button, inventory_content: str, inventory_busy: bool, restrictions: list[str], diagnoses: list[str], cuisine_types: list[str], serves: list[str], recipe_language: str, html_outputs: dict[str, str], recipe_names_by_meal: dict[str, list[str]]):
    current_meal = [meal_type.value for meal_type in (MealType) if meal_type.value in button][0]
    if inventory_busy:
        yield None, None, recipe_names_by_meal, gr.update()
        gr.Warning('Please wait for the food inventory update to finish.')
        return
    if inventory_content == INVENTORY_LIST_TITLE:
        yield None, None, recipe_names_by_meal, gr.update()
        gr.Warning('Please upload a photo first, so I can see what food items you have.')
        return

    try:
        recipes_to_exclude = [name for names in recipe_names_by_meal.values() for name in names]
        current_recipes = await get_recipes(
            current_meal,
            inventory_content.replace(INVENTORY_LIST_TITLE, '', 1).strip(),
            restrictions,
            diagnoses,
            cuisine_types,
            serves,
            recipes_to_exclude,
            language=recipe_language,
        )
        previous_recipe_names = recipe_names_by_meal.get(current_meal, [])
        current_recipe_names = [recipe['name'] for recipe in current_recipes]
        recipe_names_by_meal[current_meal] = list(dict.fromkeys(previous_recipe_names + current_recipe_names))
        labels = get_labels(recipe_language)
        current_html = recipes_template.render(recipes=current_recipes, disclaimer=labels['disclaimer_text'], labels=labels)
        html_outputs[current_meal] = current_html

        session_id = time.time_ns() # make unique session ID for anonymous user w/ timestamp
        out_file_path = _get_recipe_book_file_path(session_id)

        recipe_htmls_info = [
            {'title': labels[f'meal_{MealType(meal_type).name.lower()}'], 'id_slug': MealType(meal_type).name, 'html_string': html_string}
            for meal_type, html_string in html_outputs.items()
        ]
        _create_html_recipe_book(recipe_htmls_info, out_file_path, labels)
        yield current_html, gr.update(interactive=True, value=out_file_path), recipe_names_by_meal, gr.update(visible=True) # download_button, back-to-top link

    except Exception as e:
        logger.error(e)
        yield None, None, recipe_names_by_meal, gr.update()
        gr.Warning('Sorry, please try again.')

def _get_recipe_book_file_path(session_id: int) -> str:
    return f'{USER_DATA_DIR}/{RECIPE_BOOK_TITLE}_{session_id}.html'

def _create_html_recipe_book(recipe_htmls_info: list[dict[str, str]], out_file_path: str, labels: dict[str, str] | None = None) -> None:
    labels = labels or get_labels()
    sections_data = []

    for item_info in recipe_htmls_info:
        soup = BeautifulSoup(item_info['html_string'], 'html.parser')

        recipe_containers = soup.find_all('div', class_='recipe-container')
        section_recipes_html_content = ''.join(str(container) for container in recipe_containers)
        section_id = f"{item_info['id_slug']}-section"

        sections_data.append({
            'title': item_info['title'],
            'id': section_id,
            'html_content': section_recipes_html_content,
            'recipe_names': [c.find('h2').get_text(strip=True) for c in recipe_containers if c.find('h2')]
        })

    book_html = combined_recipes_template.render(
        book_title=f'{RECIPE_BOOK_TITLE}{FRUITICONS}',
        sections=sections_data,
        disclaimer=labels['disclaimer_text'],
        labels=labels
    )
    with open(out_file_path, 'w', encoding=UTF8_ENCODING) as f:
        f.write(book_html)
    logger.info(f'Wrote recipe book to: {out_file_path}')

async def download_chat_summary(chat_history: list[dict[str, str]]):
    ''' Generate the chat-summary HTML on demand (when the button is clicked) and
    return its file path for the browser to download. The summary is an expensive
    LLM call, so this runs only on click. '''
    # Generator so the button acts as its own wait indicator: first yield a
    # disabled "Generating…" button (trigger value unchanged), then do the
    # expensive LLM work, then yield the trigger file path and restore the button.
    # Yields are (trigger value, button update).
    yield gr.update(), gr.update(value='Generating chat summary…⏳', interactive=False)

    try:
        summary_markdown = await get_chat_summary(chat_history)
    except Exception as e:
        logger.error(e)
        gr.Warning("Sorry, the chat summary couldn't be generated. Please try again.")
        yield gr.update(), gr.update(value='Download My Chat Summary⚡', interactive=True)
        return

    summary_html = _markdown.render(summary_markdown)

    session_id = time.time_ns()
    out_file_path = f'{USER_DATA_DIR}/Chat Summary_{session_id}.html'
    page_html = chat_summary_template.render(
        title=CHAT_SUMMARY_TITLE,
        summary_html=summary_html,
    )
    with open(out_file_path, 'w', encoding=UTF8_ENCODING) as f:
        f.write(page_html)
    logger.info(f'Wrote chat summary to: {out_file_path}')

    yield out_file_path, gr.update(value='Download My Chat Summary⚡', interactive=True)

# --- Layout ---

def create_back_to_page_top_link(visible: bool = True) -> gr.HTML:
    # Scroll to the true top of the page. A bare href="#page-top" lands on the
    # title anchor, which leaves the top components looking clipped, so scroll
    # the window (and any scrollable ancestor) all the way to 0 instead.
    onclick = (
        "event.preventDefault();"
        "window.scrollTo({top:0,behavior:'smooth'});"
        "document.scrollingElement&&document.scrollingElement.scrollTo({top:0,behavior:'smooth'});"
    )
    return gr.HTML(
        "<div style='text-align: right; margin: 0; padding: 0;'>"
        f"<a href='#page-top' onclick=\"{onclick}\" style='cursor:pointer;'>Back to top</a>"
        "</div>",
        elem_id='back-to-top-link',
        visible=visible,
    )

with gr.Blocks(title=TITLE, fill_width=True) as demo:

    with gr.Row():
        gr.HTML(f'<div id="page-top" style="margin:0;"><h1 style="margin:0;">{TITLE} 🍽️</h1></div>')
        with gr.Column(scale=0, min_width=175, elem_id='recipe-language-group'):
            gr.HTML(
                '<svg id="recipe-language-caption" width="175" height="24" viewBox="0 0 175 24" '
                'xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" '
                'role="img" aria-label="Recipe language">'
                # Top edge with rounded top corners, and the two sides running all
                # the way to the bottom (no bottom border), so the caption visually
                # connects to the dropdown below it.
                '<path d="M0.5 24 L0.5 7 Q0.5 1.5 6 1.5 L169 1.5 Q174.5 1.5 174.5 7 L174.5 24" '
                'fill="none" stroke="#888" stroke-width="1"/>'
                '<text x="87.5" y="16" text-anchor="middle" font-family="sans-serif" '
                'font-size="12" fill="#444">Recipe language</text>'
                '</svg>',
                elem_id='recipe-language-caption-wrap',
                padding=False,
            )
            recipe_language_dropdown = gr.Dropdown(
                label='🇨🇭 Recipe language',
                choices=[
                    'English',
                    'Deutsch',
                    'Français',
                    'Italiano',
                    'Rumantsch',
                ],
                value='English',
                interactive=True,
                multiselect=False,
                filterable=False,
                container=False,
                scale=0,
                min_width=175,
                elem_id='recipe-language-dropdown'
            )
        gen_recipes_buttons: list[gr.Button] = []
        for meal_type in (MealType):
            gen_recipes_buttons.append(gr.Button(f'😋Get {meal_type.value} Recipes', elem_id=meal_type.name, scale=0))

    file_select = gr.File(label=f"Upload photos of what's in your fridge, freezer, kitchen cupboard, ...{FRUITICONS}", container=True, file_types=['.jpg', '.jpeg', '.png', '.gif', '.webp'], elem_id='inventory-file-upload')

    with gr.Row():
        restrictions_dropdown = gr.Dropdown(label='Dietary Restrictions', choices=yield_lines_from_file('dietary_restrictions.txt'), interactive=True, multiselect=True, value=None)
        diagnoses_dropdown = gr.Dropdown(label='Medical Diagnoses', choices=yield_lines_from_file('medical_diagnoses.txt'), interactive=True, multiselect=True, value=None)
        cuisines_dropdown = gr.Dropdown(label='Types of Cuisines', choices=yield_lines_from_file('cuisine_types.txt'), interactive=True, multiselect=True, value=None)
        serves_dropdown = gr.Dropdown(label='Serves', choices=yield_lines_from_file('serves.txt'), interactive=True, multiselect=True, value=None)

    with gr.Row():
        with gr.Column(scale=2):
            inventory_pic = gr.Image(label='Food Inventory Pic', buttons=['download', 'fullscreen'], interactive=False)
            with gr.Row():
                more_foods = gr.Textbox(submit_btn=True, show_label=False, container=False, placeholder='Update inventory instruction -- for example: Add 2 apples and remove the milk.\nℹ️ You can type or use the Record button, then click Send.', lines=3, max_lines=5)
                voice_input = gr.Audio(
                    show_label=False,
                    container=False,
                    sources=['microphone'],
                    type='filepath',
                    interactive=True,
                    waveform_options=gr.WaveformOptions(show_recording_waveform=False),
                    elem_id='voice-input',
                    scale=0,
                    min_width=110
                )
                clear_inventory_button = gr.Button('Clear inventory', scale=0)
        with gr.Column(scale=1):
            inventory_status = gr.Markdown('', visible=False, container=False)
            inventory_list = gr.Markdown(INVENTORY_LIST_TITLE, container=True, buttons=['copy'], height='60vh')
            inventory_state = gr.State([])
        with gr.Column(scale=1, elem_id='fridge-chef-panel'):
            fridge_chef_fullscreen_button = gr.Button(
                '⛶',
                size='sm',
                elem_id='fridge-chef-fullscreen-button',
                min_width=30
            )
            fridge_chef_chat = gr.Chatbot(
                value=[{
                    'role': 'assistant',
                    'content': FRIDGE_CHEF_DISABLED_GREETING
                }],
                label='Ask your Fridge Chef',
                height='calc(60vh - 90px)',
                buttons=['copy_all'],
                layout='bubble',
                avatar_images=(None, 'images/fridge_chef_avatar.svg'),
                elem_id='fridge-chef-chat'
            )
            fridge_chef_history_state = gr.State([{
                'role': 'assistant',
                'content': FRIDGE_CHEF_DISABLED_GREETING
            }])
            fridge_chef_busy_state = gr.State(False)
            inventory_busy_state = gr.State(False)
            with gr.Row(elem_id='fridge-chef-input-row'):
                fridge_chef_message = gr.Textbox(
                    submit_btn=True,
                    show_label=False,
                    container=False,
                    placeholder='Ask about your inventory in your language…',
                    lines=2,
                    max_lines=4,
                    interactive=False
                )
                fridge_chef_voice_input = gr.Audio(
                    show_label=False,
                    container=False,
                    sources=['microphone'],
                    type='filepath',
                    interactive=True,
                    visible=False,
                    waveform_options=gr.WaveformOptions(show_recording_waveform=False),
                    elem_id='fridge-chef-voice-input',
                    scale=0,
                    min_width=110
                )
                fridge_chef_disabled_record = gr.Button('Record', interactive=False, elem_id='fridge-chef-disabled-record', scale=0, min_width=110)

    fridge_chef_fullscreen_button.click(
        fn=None,
        js='''() => {
            const panel = document.getElementById('fridge-chef-panel');
            const button = document.getElementById('fridge-chef-fullscreen-button');
            if (!panel || !button) return;
            const expanded = panel.classList.toggle('fridge-chef-fullscreen');
            document.body.classList.toggle('fridge-chef-fullscreen-open', expanded);
        button.textContent = expanded ? '×' : '⛶';
            button.setAttribute('aria-label', expanded ? 'Exit fullscreen chat' : 'Enter fullscreen chat');
            button.title = expanded ? 'Exit fullscreen chat (Esc)' : 'Enter fullscreen chat';

            if (window.fridgeChefFullscreenEscapeBound) return;
            window.fridgeChefFullscreenEscapeBound = true;
            document.addEventListener('keydown', (event) => {
                if (event.key !== 'Escape') return;
                const activePanel = document.getElementById('fridge-chef-panel');
                if (!activePanel?.classList.contains('fridge-chef-fullscreen')) return;
                activePanel.classList.remove('fridge-chef-fullscreen');
                document.body.classList.remove('fridge-chef-fullscreen-open');
                const activeButton = document.getElementById('fridge-chef-fullscreen-button');
                if (activeButton) {
                    activeButton.textContent = '⛶';
                    activeButton.setAttribute('aria-label', 'Enter fullscreen chat');
                    activeButton.title = 'Enter fullscreen chat';
                }
            });

            // --- Diagnostic (negligible cost): catch the intermittent bug where
            // the chat inputs scroll off the viewport in fullscreen. A single
            // ResizeObserver on the input row (set up once) fires only when that
            // row actually changes size, and logs geometry ONLY when its bottom
            // crosses below the viewport while fullscreen is active. Silent and
            // effectively free otherwise. Captured so the bug can be diagnosed
            // from real data whenever it next occurs.
            // NOTE: This bug has not been observed since the "Thinking..." bubble
            // wrapping fix (bot bubble max-width 70% -> 70ch), but it was always
            // intermittent so that is not proof it is gone. The old 70% could
            // collapse the bot bubble's box in fullscreen, which may also have
            // mis-sized the chat column and pushed the inputs off-screen -- so the
            // wrapping fix may have resolved this too. Left in place to confirm.
            if (!window.fridgeChefInputObserver && 'ResizeObserver' in window) {
                const inputRow = document.getElementById('fridge-chef-input-row');
                const panel = document.getElementById('fridge-chef-panel');
                if (inputRow && panel) {
                    window.fridgeChefInputObserver = new ResizeObserver(() => {
                        if (!panel.classList.contains('fridge-chef-fullscreen')) return;
                        const r = inputRow.getBoundingClientRect();
                        const vh = window.innerHeight;
                        if (r.bottom > vh + 1 || r.top >= vh) {
                            console.warn('[fridge-chef] inputs off-screen in fullscreen',
                                JSON.stringify({
                                    viewport: Math.round(vh),
                                    inputTop: Math.round(r.top),
                                    inputBottom: Math.round(r.bottom),
                                    panelBottom: Math.round(panel.getBoundingClientRect().bottom),
                                    panelHeight: Math.round(panel.getBoundingClientRect().height),
                                }));
                        }
                    });
                    window.fridgeChefInputObserver.observe(inputRow);
                }
            }
        }''',
        show_progress='hidden'
    )

    with gr.Row(elem_id='recipes-row'):
        recipes_html_outputs: list[gr.HTML] = []
        back_to_top_links: list[gr.HTML] = []
        for meal_type in (MealType):
            with gr.Column(elem_classes='recipe-column'):
                recipes_html_outputs.append(gr.HTML(label=f'{meal_type.value} Recipes', elem_id=meal_type.name, container=True, show_label=True))
                back_to_top_links.append(create_back_to_page_top_link(visible=False))

    with gr.Row(elem_id='download-row'):
        download_button = gr.DownloadButton('Download My Recipe Book⚡', interactive=False, scale=0)
        # Generate strictly on click (the summary is an expensive LLM call, so it
        # must NOT run on every chat turn). A plain button runs generation; its
        # result sets a hidden DownloadButton's value, and a chained JS step clicks
        # that hidden link to fire the browser download in the same user gesture
        # (this also avoids the two-click issue of generating and downloading from
        # the same DownloadButton click).
        chat_summary_button = gr.Button('Download My Chat Summary⚡', interactive=False, scale=0, elem_id='chat-summary-download')
        chat_summary_download_trigger = gr.DownloadButton(visible='hidden', elem_id='chat-summary-download-trigger')

    # Footer
    gr.HTML(f'''
        <div id='app-footer' style='text-align: center;'>
            Powered by <a href='https://apertus-ai.org/' target='_blank'>Apertus {SWISS_FLAG_SVG_INLINE} Switzerland’s sovereign LLM</a>
        </div>
    ''')

    html_outputs_state = gr.State({})
    recipe_names_by_meal_state = gr.State({})

    inventory_busy_state.change(
        get_recipe_button_updates,
        inputs=[inventory_busy_state],
        outputs=gen_recipes_buttons,
        show_progress='hidden'
    )

    fridge_chef_submit_event = fridge_chef_message.submit(
        submit_fridge_chef_message,
        inputs=[fridge_chef_message, inventory_state, fridge_chef_history_state],
        outputs=[fridge_chef_chat, fridge_chef_history_state, fridge_chef_message, fridge_chef_voice_input, fridge_chef_disabled_record, fridge_chef_busy_state],
        show_progress='hidden'
    )

    fridge_chef_submit_event.then(
        get_fridge_chef_control_updates,
        inputs=[inventory_state, fridge_chef_busy_state, inventory_busy_state],
        outputs=[fridge_chef_message, fridge_chef_voice_input, fridge_chef_disabled_record],
        show_progress='hidden'
    )

    # Enable the chat-summary download after a chat turn (history now has a user
    # message). Chained off the submit event rather than State.change, which does
    # not fire reliably for a generator's streamed yields.
    fridge_chef_submit_event.then(
        get_chat_summary_button_update,
        inputs=[fridge_chef_history_state],
        outputs=[chat_summary_button],
        show_progress='hidden'
    )

    # On click: generate the summary (expensive LLM call) and set the hidden
    # DownloadButton's value, then programmatically click that hidden link to
    # trigger the browser download in the same user gesture. The handler is a
    # generator that updates the button label to "Generating…" during the call,
    # so the button itself serves as the wait indicator.
    chat_summary_button.click(
        download_chat_summary,
        inputs=[fridge_chef_history_state],
        outputs=[chat_summary_download_trigger, chat_summary_button],
        show_progress='hidden'
    ).then(
        fn=None,
        js='''() => {
            const trigger = document.querySelector('#chat-summary-download-trigger a')
                || document.querySelector('#chat-summary-download-trigger');
            if (!trigger) { return; }
            trigger.click();
            // Ring the "order up!" bell to call the user back for the download.
''' + RING_KITCHEN_BELL_JS_BODY + '''
        }'''
    )

    process_image_event = file_select.upload(
        process_image,
        inputs=[file_select, inventory_state, inventory_list, fridge_chef_history_state, fridge_chef_busy_state, recipe_language_dropdown],
        outputs=[file_select, inventory_pic, inventory_state, inventory_list, inventory_status, fridge_chef_message, fridge_chef_voice_input, fridge_chef_disabled_record, inventory_busy_state],
        show_progress='hidden'
    )

    process_image_event.then(
        get_fridge_chef_greeting_updates,
        inputs=[inventory_state, fridge_chef_history_state],
        outputs=[fridge_chef_chat, fridge_chef_history_state],
        show_progress='hidden'
    )

    process_image_event.then(
        get_fridge_chef_control_updates,
        inputs=[inventory_state, fridge_chef_busy_state, inventory_busy_state],
        outputs=[fridge_chef_message, fridge_chef_voice_input, fridge_chef_disabled_record],
        show_progress='hidden'
    )

    update_inventory_event = more_foods.submit(
        update_foods_in_inventory,
        inputs=[more_foods, inventory_state, inventory_list, fridge_chef_history_state, fridge_chef_busy_state, recipe_language_dropdown],
        outputs=[inventory_state, inventory_list, more_foods, inventory_status, fridge_chef_message, fridge_chef_voice_input, fridge_chef_disabled_record, inventory_busy_state],
        show_progress='hidden'
    )

    update_inventory_event.then(
        get_fridge_chef_greeting_updates,
        inputs=[inventory_state, fridge_chef_history_state],
        outputs=[fridge_chef_chat, fridge_chef_history_state],
        show_progress='hidden'
    )

    update_inventory_event.then(
        get_fridge_chef_control_updates,
        inputs=[inventory_state, fridge_chef_busy_state, inventory_busy_state],
        outputs=[fridge_chef_message, fridge_chef_voice_input, fridge_chef_disabled_record],
        show_progress='hidden'
    )

    voice_input.stop_recording(
        append_audio_transcription,
        inputs=[voice_input, more_foods],
        outputs=[more_foods, voice_input]
    )

    fridge_chef_voice_input.stop_recording(
        append_audio_transcription,
        inputs=[fridge_chef_voice_input, fridge_chef_message],
        outputs=[fridge_chef_message, fridge_chef_voice_input]
    )

    clear_inventory_event = clear_inventory_button.click(
        clear_inventory,
        inputs=[fridge_chef_history_state, fridge_chef_busy_state],
        outputs=[inventory_state, inventory_list, more_foods, inventory_status, fridge_chef_message, fridge_chef_voice_input, fridge_chef_disabled_record, inventory_busy_state],
        show_progress='hidden'
    )

    clear_inventory_event.then(
        get_fridge_chef_greeting_updates,
        inputs=[inventory_state, fridge_chef_history_state],
        outputs=[fridge_chef_chat, fridge_chef_history_state],
        show_progress='hidden'
    )

    fridge_chef_chat.clear(
        clear_fridge_chef_chat,
        inputs=[inventory_state],
        outputs=[fridge_chef_chat, fridge_chef_history_state, fridge_chef_busy_state, fridge_chef_message, fridge_chef_voice_input, fridge_chef_disabled_record],
        show_progress='hidden',
        cancels=[fridge_chef_submit_event]
    ).then(
        get_chat_summary_button_update,
        inputs=[fridge_chef_history_state],
        outputs=[chat_summary_button],
        show_progress='hidden'
    )

    # Rings the shared bell, but only when real recipe content loaded (so the
    # early-guard/error yields that pass empty HTML stay silent).
    ring_kitchen_bell_js = '''
    (recipesHtml) => {
        if (!recipesHtml || !recipesHtml.includes('recipe-container')) { return; }
''' + RING_KITCHEN_BELL_JS_BODY + '''
    }
    '''

    for button in gen_recipes_buttons:
        output_index = [i for i, output in enumerate(recipes_html_outputs) if output.elem_id == button.elem_id][0]
        html_output = recipes_html_outputs[output_index]
        back_to_top_link = back_to_top_links[output_index]
        # Scroll to the recipes row immediately on click (before generation runs)
        # so the user sees the processing indicator while the LLM works. Skip the
        # scroll when the inventory is empty, since generation won't start then
        # (the handler shows an "upload a photo first" warning instead).
        button.click(
            fn=None,
            inputs=[inventory_list],
            js='''(inventoryMarkdown) => {
                const emptyTitle = ''' + repr(INVENTORY_LIST_TITLE) + ''';
                if (!inventoryMarkdown || inventoryMarkdown.trim() === emptyTitle.trim()) { return; }
                const row = document.getElementById('recipes-row');
                if (row) { row.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
            }'''
        )
        button.click(
            gen_recipes_for_meal,
            inputs=[button, inventory_list, inventory_busy_state, restrictions_dropdown, diagnoses_dropdown, cuisines_dropdown, serves_dropdown, recipe_language_dropdown, html_outputs_state, recipe_names_by_meal_state],
            outputs=[html_output, download_button, recipe_names_by_meal_state, back_to_top_link]
        ).then(
            # Ring the kitchen "order up!" bell once the recipes have loaded.
            fn=None,
            inputs=[html_output],
            js=ring_kitchen_bell_js,
        )

demo.launch(server_name='0.0.0.0', theme=gr.themes.Monochrome(), css='''
    footer {visibility: hidden}

    /* Recipe-language selector: an SVG caption (its own bordered box, immune to
       flex-layout issues) stacked above a compact dropdown. The caption clarifies
       the dropdown only sets the recipe language (not the whole UI). */
    #recipe-language-group {
        gap: 0 !important;   /* caption side-borders touch the dropdown below */
    }
    /* Collapse the caption's gr.HTML wrapper AND its inner Gradio elements to the
       SVG height (the inner .prose/.block carried a min-height adding ~28px, making
       the group taller than the buttons). The only content is the SVG, so forcing
       every descendant to the SVG height is safe. */
    #recipe-language-caption-wrap,
    #recipe-language-caption-wrap * {
        min-height: 0 !important;
        max-height: 24px !important;
        height: 24px !important;
        padding: 0 !important;
        margin: 0 !important;
        line-height: 24px !important;
    }
    #recipe-language-caption-wrap {
        flex: 0 0 auto !important;
    }
    #recipe-language-caption {
        display: block !important;
        width: 175px !important;
        height: 24px !important;
        margin: 0 auto !important;
    }

    #recipe-language-dropdown {
        min-height: 42px !important;
    }

    #recipe-language-dropdown .wrap {
        min-height: 42px !important;
    }

    #recipe-language-dropdown input[role="combobox"] {
        padding-left: 40px !important;
        padding-right: 36px !important;
        background-image: url("data:image/svg+xml;base64,__SWISS_FLAG_B64__") !important;
        background-size: 22px 22px !important;
        background-position: 8px center !important;
        background-repeat: no-repeat !important;
    }

    /* Trim the container's default vertical margin. Full width is handled by
       fill_width=True on gr.Blocks. */
    .gradio-container {
        margin: 5px 0px 5px 0px !important; /* top, right, bottom, left */
    }

    @media (min-width: 901px) {
        #inventory-file-upload .upload-container {
            height: 130px !important;
        }
    }

    /* Highlight the photo-upload component so it stands out as the place to add
       food photos, distinct from the other default-background components. */
    #inventory-file-upload {
        background: #fffaf2 !important;          /* soft warm tint */
        border: 1px solid #f0d6a8 !important;    /* gentle highlight border */
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(232, 163, 61, 0.12) !important;
        transition: background 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease !important;
    }
    #inventory-file-upload:hover {
        background: #fff3df !important;
        border-color: #e8a33d !important;
        box-shadow: 0 2px 6px rgba(232, 163, 61, 0.25) !important;
    }
    /* Keep the inner upload area transparent so the tint shows through, and give
       the "Click to Upload" text room so it doesn't sit on the bottom border. */
    #inventory-file-upload .upload-container,
    #inventory-file-upload .wrap {
        background: transparent !important;
    }
    #inventory-file-upload .wrap {
        padding-top: 10px !important;
        padding-bottom: 14px !important;
    }

    /* Compact the Gradio 6 microphone widget to its Record/Stop controls. */
    [id$="voice-input"] .mic-select,
    [id$="voice-input"] .duration-button,
    [id$="voice-input"] .icon-button-wrapper {
        display: none !important;
    }

    [id$="voice-input"] .audio-container {
        min-height: 0 !important;
        height: auto !important;
    }

    [id$="voice-input"] .component-wrapper {
        padding: 0 !important;
    }

    [id$="voice-input"] .mic-wrap {
        margin: 0 !important;
    }

    [id$="voice-input"] .stop-button {
        background: #dc2626 !important;
        border-color: #dc2626 !important;
        color: white !important;
        font-weight: 600 !important;
    }

    [id$="voice-input"] .stop-button::before {
        background: white !important;
        animation: voice-recording-pulse 1.2s ease-in-out infinite !important;
    }

    #fridge-chef-disabled-record:is(button),
    #fridge-chef-disabled-record button {
        width: var(--size-24) !important;
        min-width: var(--size-24) !important;
        height: var(--size-8) !important;
        min-height: var(--size-8) !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
        justify-content: center !important;
        font-size: var(--text-md) !important;
        line-height: 1 !important;
        white-space: nowrap !important;
    }

    #fridge-chef-disabled-record:is(button)::before,
    #fridge-chef-disabled-record button::before {
        content: "";
        width: var(--size-4);
        height: var(--size-4);
        flex-shrink: 0;
        margin-right: var(--spacing-xl);
        border-radius: var(--radius-full);
        background: var(--primary-600);
    }

    #fridge-chef-chat .message.bot {
        background: #f5f1e8 !important;
        border-color: #d8d0c2 !important;
        color: #292621 !important;
    }

    #fridge-chef-chat .bot-row.bubble > .avatar-container {
        margin-right: 6px !important;
    }

    #fridge-chef-chat .message-row.bot-row.bubble {
        margin-left: 8px !important;
    }

    #fridge-chef-chat .message.user {
        background: #e8eef8 !important;
        border-color: #bdcbe1 !important;
        color: #172033 !important;
    }

    #fridge-chef-fullscreen-button:is(button),
    #fridge-chef-fullscreen-button button {
        position: absolute !important;
        top: 3px !important;
        right: 60px !important;
        z-index: 10 !important;
        width: 30px !important;
        min-width: 30px !important;
        height: 30px !important;
        min-height: 30px !important;
        padding: 0 !important;
        font-size: 22px !important;
        line-height: 1 !important;
    }

    #fridge-chef-panel {
        position: relative !important;
    }

    body.fridge-chef-fullscreen-open {
        overflow: hidden !important;
    }

    #fridge-chef-panel.fridge-chef-fullscreen {
        position: fixed !important;
        inset: 0 !important;
        z-index: 10000 !important;
        width: 100vw !important;
        max-width: none !important;
        height: 100dvh !important;
        padding: 12px !important;
        background: var(--body-background-fill) !important;
        box-sizing: border-box !important;
    }

    #fridge-chef-panel.fridge-chef-fullscreen #fridge-chef-fullscreen-button:is(button),
    #fridge-chef-panel.fridge-chef-fullscreen #fridge-chef-fullscreen-button button {
        top: 12px !important;
        right: 74px !important;
        font-size: 18px !important;
    }

    #fridge-chef-panel.fridge-chef-fullscreen #fridge-chef-chat {
        flex: 1 1 auto !important;
        min-height: 0 !important;
        height: calc(100dvh - 110px) !important;
        max-height: none !important;
    }

    /* Cap bot bubble line length in fullscreen by text measure (ch), not a
       percentage. A % here resolves against the bubble's content-sized container,
       so a short bubble like "Thinking..." collapsed to a sliver and wrapped;
       a ch-based max caps long replies without shrinking short ones. */
    #fridge-chef-panel.fridge-chef-fullscreen #fridge-chef-chat .message.bot {
        max-width: 70ch !important;
    }

    @keyframes voice-recording-pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.45; transform: scale(1.3); }
    }

    /* --- "Back to top" convenience link under each recipe column --- */
    /* Collapse the vertical space around the link. */
    #back-to-top-link {
        padding: 0 !important;
        margin: 0 !important;
        min-height: 0 !important;
    }
    #back-to-top-link > * {
        padding: 0 !important;
        margin: 0 !important;
    }
    /* Remove the gap Gradio inserts between the recipe HTML and the link below it. */
    .recipe-column {
        gap: 4px !important;
    }
    /* Pull the Download button row up tight under the "Back to top" link.
       The space is the parent flex container's gap, not this row's margin, so a
       negative top margin is used to overcome it. */
    #download-row {
        margin-top: -24px !important;
        padding-top: 0 !important;
    }
    /* Recolor the ⚡ on the chat-summary button so its lightning is a different
       hue than the yellow bolt on the recipe-download button. The emoji is a fixed
       yellow glyph, so a hue-rotate filter shifts its color. */
    #chat-summary-download {
        filter: hue-rotate(180deg) saturate(1.4) !important;
    }

    /* Inline Swiss flag in the footer link: size to the text and keep it inline
       (inline SVG attributes were being ignored, so it rendered huge and broke
       onto its own line). */
    #app-footer .swiss-flag-inline {
        display: inline-block !important;
        width: 1em !important;
        height: 1em !important;
        vertical-align: -0.15em !important;
        margin: 0 0.15em !important;
    }
    '''.strip().replace('__SWISS_FLAG_B64__', SWISS_FLAG_SVG_B64))
