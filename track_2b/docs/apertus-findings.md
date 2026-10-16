# Apertus model findings

This document reports behaviours of the Apertus 1.5 model family observed while building
AI Fridge Chef, offered as constructive feedback to the Apertus team. Each finding
includes the conditions needed to reproduce it and the concrete evidence collected.

## Environment

- **Models:** `swiss-ai/Apertus-v1.5-70B` (instruct), `swiss-ai/Apertus-v1.5-8B` (lite),
  and `swiss-ai/Apertus-v1.5-70B-thinking` (reasoning).
- **Endpoint:** CSCS inference service, OpenAI-compatible API, accessed via LangChain's
  `ChatOpenAI`.
- **Sampling:** `temperature=0` for all calls.
- **Method:** each behaviour was probed with multiple prompt revisions and, where noted,
  with more than one model variant. Testing relied on clear, principle-based instructions
  rather than heavy few-shot engineering, so these findings largely reflect behaviour
  under direct instruction.

The findings are grouped by capability: language and localization, generation and
instruction-following, grounding and safety, multimodal (vision and speech), and
serving/operability.

---

## Language and localization

### 1. Locale mention biases *language* selection

**Model:** `Apertus-v1.5-70B`.

**Reproduce:** In a prompt where the response language is inferred from the user's
messages, add an instruction to "assume a Switzerland locale" (intended to affect only
regional spelling/vocabulary/units). Send a short, borderline English request such as
"Please give me a dinner recipe."

**Observed:** With the locale instruction present, the model answered entirely in German —
reproducibly (4/4, then 5/5 runs). Removing the instruction restored English (4/4). The
bias persisted regardless of the instruction's placement in the prompt, its wording, and
an explicit "this must not change the response language" guard. The mere presence of
"Switzerland"/"Swiss" near the language-selection logic was enough to pull a borderline
request into German.

**Impact:** A locale/regional-convention instruction should not change *which language*
the model answers in. Here it overrides language inference for short or ambiguous inputs.

### 2. Output language not taken from the most recent message after a mid-conversation language switch

**Model:** `Apertus-v1.5-70B-thinking` (observed in the chat summary; the chat path on
`Apertus-v1.5-70B` is also affected).

**Reproduce:** Hold a conversation that starts in one language (English) and switch to
another partway through (French). Ask for output (e.g. a summary) that should follow the
latest language used.

**Observed:** The output was produced in the *earlier* language (English) rather than the
most recent (French). Conversations conducted consistently in a single language produced
the correct language — the failure is specific to the mid-conversation switch. An explicit
instruction to use the language of the user's most recent message and ignore earlier
languages worked for single-language chats but did not reliably override on switch chats.

### 3. Swiss Standard German: emits "ß" instead of "ss"

**Model:** `Apertus-v1.5-70B` (both chat and recipe output).

**Reproduce:** Request German output and instruct the model to use Swiss Standard German
orthography, which has no "ß" (every "ß" should be "ss", e.g. "gross", "heiss",
"geniessen").

**Observed:** The model regularly produced Germany-convention "ß" even when the prompt
explicitly and repeatedly required Swiss "ss" spelling. It got Swiss *vocabulary* right
(e.g. "Nachtessen") but not the orthography. A sample reply started at 6 "ß" occurrences;
escalating prompt techniques (prominence, an explicit list of word rewrites, a few-shot
example line, a self-check step) reduced the count but never reliably reached zero — even
words explicitly listed as "ß → ss" still slipped through, and compliance varied per
generation.

---

## Generation and instruction-following

### 4. Macronutrient percentages do not reliably sum to 100

**Model:** `Apertus-v1.5-8B` and `Apertus-v1.5-70B` (recipe-generation path; observed on
both, explicitly including 70B).

**Reproduce:** In a structured recipe-generation prompt, require the three macronutrient
percentages (carbohydrate, fat, protein) to total 100% for every recipe.

**Observed:** Recipes frequently totalled 75%, 80%, 60%, etc. Even the 70B model ignored
the explicit 100% rule on some recipes within an otherwise-correct batch. The rule was
followed inconsistently across generations.

### 5. Explicit serving-size mapping ignored (8B)

**Model:** `Apertus-v1.5-8B` (the 70B model honoured the mapping more reliably).

**Reproduce:** Provide a serving-size value with an explicit mapping (e.g. "Couple (2)" →
`"2"`) and require the output field to use the mapped value.

**Observed:** The 8B model returned `serves: "2-4"` on every recipe instead of `"2"` — a
tested condition that failed every time. The 70B model honoured the mapping more reliably.

### 6. Output-schema violations (invents fields)

**Model:** `Apertus-v1.5-8B` and `Apertus-v1.5-70B` (recipe-generation path; observed on
both).

**Reproduce:** Request a fixed JSON schema where any added ingredients must go inside each
recipe's `notes` field.

**Observed:** The model repeatedly added an undocumented root-level `added_ingredients`
property outside the requested schema, and those added-ingredient lists were often
incomplete (omitting items such as olive oil, lemon juice, salt, and pepper that the
recipe itself used). The JSON still parsed, but the structure did not match the contract.

### 7. Semantic uniqueness fails under an exclusion list (near-duplicate outputs)

**Model:** `Apertus-v1.5-8B` and `Apertus-v1.5-70B` (recipe-generation path; the
constraint-degradation under a growing exclusion list was most pronounced on 8B).

**Reproduce:** Ask for several recipes, then on retry pass the previously generated recipe
names in an exclusion list and request genuinely different recipes.

**Observed:** Exact-name exclusion worked (no identical names across retries), but the
model produced near-duplicates — repeated variations of "Swiss-inspired vegetable and egg
stir-fry" across all three retry batches. As the exclusion list grew, the 8B model
degraded on other constraints (abandoning the requested cuisine entirely in a later
batch). The model treats exclusion as name-avoidance rather than a request for
semantically distinct outputs.

### 8. Reasoning model cannot reliably collapse refined variations in a summary

**Model:** `Apertus-v1.5-70B-thinking` (also seen on the `Apertus-v1.5-70B` instruct model
before switching to the reasoning variant).

**Reproduce:** Hold a conversation that refines a single recipe across several messages
(e.g. change an ingredient count, then switch cooking method stovetop → oven). Ask the
reasoning model (`-thinking`) to summarize, keeping only the final version of each recipe
while retaining genuinely different dishes.

**Observed:** Inconsistent. The model frequently emitted every version as a separate
recipe, even labelling them "initial version", "adapted to 3 sausages", "oven" — i.e. it
demonstrably *understands* they are versions of one recipe, but will not suppress the
superseded ones. The behaviour was non-deterministic (same conversation, same
`temperature=0`, different results across runs) and degraded as the chain of variations
grew: a 2-version chain sometimes collapsed correctly, a 3-version chain kept all three.
Switching from the instruct model to `-thinking` and raising the thinking token budget to
100k (to rule out truncated reasoning) improved simple cases but remained unreliable on
complex ones.

### 9. Invents details not present in the input

**Model:** `Apertus-v1.5-70B-thinking` (chat-summary path).

**Reproduce:** Ask the model to summarize a conversation and include only what was
actually discussed.

**Observed:** The summary routinely added a serving size (e.g. "Serves: 2–3 people",
"Portions : 2 personnes") that never appeared in the source conversation. The values were
usually plausible estimates derived from ingredient quantities, but they are fabrications
relative to the input. An explicit "do not invent any detail such as a serving size"
instruction did not reliably stop it.

---

## Grounding and safety

### 10. Ignores dietary / medical constraints, including an unsafe suggestion

**Model:** `Apertus-v1.5-8B` and `Apertus-v1.5-70B` (recipe-generation path; observed on
both).

**Reproduce:** Generate recipes with dietary restrictions and medical considerations
selected — e.g. "low sodium" together with high blood pressure.

**Observed:** Recipes repeatedly added salt (~¼ tsp, ≈575 mg sodium) despite the
low-sodium + high-blood-pressure selection, and treated sodium-heavy Swiss cheese as
compatible with "low sodium". In one case the model suggested a **potassium-chloride salt
substitute**, which can be unsafe for people with kidney issues or on certain
blood-pressure medication. This is a genuine safety concern, not merely non-compliance.
Passing the constraints explicitly in the prompt did not make compliance reliable.

### 11. Builds recipes on unidentified ingredients (food-safety risk)

**Model:** `Apertus-v1.5-8B` and `Apertus-v1.5-70B` (recipe-generation path; observed on
both).

**Reproduce:** Include a vague, unidentifiable item in the inventory (e.g. "Leftover
Container") and request recipes.

**Observed:** The model invented the contents ("assumed to be protein and vegetables",
"assumed to contain cooked brown rice or quinoa") and built recipes around them. Because
the real contents are unknown, acting on the assumption is a food-safety risk; the model
should instead decline to use an item it cannot identify.

### 12. Fabricates source citations

**Model:** `Apertus-v1.5-8B` and `Apertus-v1.5-70B` (recipe-generation path; observed on
both).

**Reproduce:** Ask the model (which has no search or tool access) to return source URLs
for the recipes it generates.

**Observed:** The model consistently returned generic or fabricated-looking URLs. With no
retrieval capability, any "source" it emits is invented, and no prompt wording could make
the citations trustworthy.

### 13. Weak and unreliable Swiss regional culinary knowledge

**Model:** `Apertus-v1.5-8B` and `Apertus-v1.5-70B` (recipe-generation path; the Romandy
example was on 70B).

**Reproduce:** Request Swiss or granular Swiss-regional recipes — e.g. select
"French-speaking Switzerland (Romandy)" — even in a simplified task (no dietary/medical/
serving constraints; just "use these foods, make Swiss dinner recipes, return this JSON").

**Observed:** "Swiss-inspired" was mostly a label on generic dishes (omelette,
tomato-cucumber salad, stir-fry). With the Romandy label, the model confused Romandy with
Italian influence (risotto, crostini) and claimed Italian influence is common in Romandy
"due to its proximity to Italy" — misleading, as French influence defines Romandy — and
missed well-known Romand dishes (papet vaudois, longeole, Fribourg fondue/cuchaule,
raclette, Malakoff). Prompt guardrails requiring recognizable regional elements, and
adding granular regional labels, nudged presentation but did not produce dependable
regional knowledge.

**Scope note:** This is a narrow conclusion about Swiss *regional culinary* knowledge in
constrained recipe tasks; it is not a claim about Swiss culture or knowledge generally.

---

## Multimodal

### 14. Vision: detects non-food objects as food (false positives)

**Model:** `Apertus-v1.5-70B`.

**Reproduce:** Submit an image containing no edible items (test case: a photo of gold
coins) to an image-food-detection prompt that should return an empty result.

**Observed:** The gold-coin image was detected as food items. A general "detect the food
in this image" instruction was not enough to make the model reliably reject non-food.
Adding explicit, somewhat redundant rules ("If the image contains no visible edible food
or beverage, return exactly `[]`" and "An image containing only non-food objects must
return `[]`") brought the test case under control (empty result, verified repeatedly). The
behaviour is reported because the model's default was to hallucinate food from clearly
non-edible objects.

### 15. Multilingual speech recognition is unreliable for short utterances

**Model:** `Apertus-v1.5-8B` and `Apertus-v1.5-70B` (both failed; per-condition results
in the table below).

**Reproduce:** Send a short spoken phrase — especially a food name — as base64 audio via
the vLLM-style `audio_url` chat message, and ask the model to transcribe it faithfully in
the spoken language. Test phrase: a clearly spoken French "gâteau chocolat".

**Observed:** Short multilingual phrases were badly misheard by both 8B and 70B. For the
same "gâteau chocolat" recording:

| Condition | Output |
|---|---|
| 8B, interpretation-leaning prompt | A fabricated inventory instruction ("The tofu should be added … quantity of 5 … increasing the expiration date by one month") — the model interpreted instead of transcribing |
| 8B, strict verbatim prompt | `Get total shotla` |
| 70B, strict verbatim prompt | `ketorolac` |
| 8B, with food-vocabulary hint | `Get tall chocolate` |
| 8B, with Swiss-language prior list | `Get toasted` (worse) |

The audio carried a strong signal (measured RMS ~13–14%), so this is not a silence,
microphone, or client-encoding problem — the word was never reliably decoded. A
direct-audio variant (sending audio plus the current inventory and asking for a proposed
inventory update) was worse: with inventory context the model anchored misheard words to
existing items — "add 2 bananas" became "Add 1 Sandwich" and "add 2 oranges" became "Add
one Orange Juice" (an *Orange Juice* item was present) — and quantities were wrong
(2 → 1). This suggests the model guesses a plausible answer from context rather than
producing a faithful transcript first. A strict verbatim-transcription prompt stopped the
extreme fabricated-instruction behaviour but not the mis-transcription itself.

---

## Operability

### 16. `-thinking` requests time out through the CSCS gateway

**Model:** `Apertus-v1.5-8B-thinking` (the timeout is a property of the reasoning-mode
path through the gateway, so `Apertus-v1.5-70B-thinking` is expected to be at least as
affected).

**Reproduce:** Call a `-thinking` model on the CSCS endpoint for a non-trivial generation,
with a generous output-token budget.

**Observed:** `8B-thinking` with `MAX_TOKENS=8000` returned HTTP 500 after ~51s; raising
the budget to a very large value caused a 504 gateway timeout at ~60s. Both failures
cluster at an apparent ~50–60s upstream limit. Thinking mode also consumes several times
more output tokens, which makes the timeout more likely rather than less. (For clarity: a
larger `MAX_TOKENS` does not enlarge the usable context window — it raises the ceiling on
*generated* tokens, increasing timeout risk.) The practical consequence is that `-thinking`
is only usable on non-interactive, latency-tolerant paths through this gateway.

---

## Summary of impact

| # | Capability | Finding | Severity |
|---|---|---|---|
| 1 | Language | Locale mention overrides language selection | Medium |
| 2 | Language | Wrong language after mid-conversation switch | Medium |
| 3 | Language | Swiss "ss" orthography not honoured | Low |
| 4 | Generation | Macro percentages don't sum to 100 | Low |
| 5 | Generation | Serving-size mapping ignored (8B) | Low |
| 6 | Generation | Invents fields outside JSON schema | Low |
| 7 | Generation | Near-duplicate outputs under exclusion list | Medium |
| 8 | Reasoning | Can't collapse refined variations in summary | Medium |
| 9 | Generation | Invents details not in the input | Medium |
| 10 | Safety | Ignores dietary/medical constraints; unsafe substitute | High |
| 11 | Safety | Builds recipes on unidentified ingredients | High |
| 12 | Grounding | Fabricates source citations | Medium |
| 13 | Knowledge | Weak Swiss regional culinary knowledge | Medium |
| 14 | Vision | Detects non-food objects as food | Medium |
| 15 | Speech | Unreliable multilingual ASR for short utterances | High |
| 16 | Operability | `-thinking` times out via CSCS gateway | Medium |

Severity reflects impact on this application's use cases, not a general ranking of the
models.
