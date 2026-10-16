# AI Fridge Chef

An Apertus-powered kitchen assistant. Snap a photo of your fridge, freezer, or pantry
and the app detects the food, lets you build an inventory (by image or voice), then
generates recipes tailored to your ingredients, dietary restrictions, and any medical
considerations — all through Switzerland's sovereign LLM, [Apertus](https://huggingface.co/swiss-ai/Apertus-v1.5-70B).

The UI is a [Gradio](https://www.gradio.app/) web app served on port **7860**.

## 🌐 Live deployment

**https://aifridgechef-d19909-wwmcheung.apps.ai-3.kvant.cloud/**

Running on the sovereign Swiss cloud of
[Phoenix Technologies AG](https://phoeniqs.com) (Pfäffikon SZ, Switzerland), with all
Apertus inference on the Swiss CSCS endpoint — so hosting and inference alike stay within
Swiss jurisdiction.

---

## Prerequisites

- **Docker** installed and running.
  - Linux: Docker Engine.
  - Windows/macOS: Docker Desktop (on Windows, use the WSL2 backend and run `make`
    from inside a WSL distro).
- **`make`** (for the `make run` path; see the alternative below if you don't have it).
- An **Apertus API key** for the CSCS inference endpoint.

---

## 1. Configure the environment

The app reads its configuration from `src/.env`. This file is **baked into the Docker
image at build time**, so it must exist and contain real values *before* you build.

From the `track_2b/` directory, copy the sample:

```bash
cp src/.env_sample src/.env            # bash / WSL / macOS
Copy-Item src/.env_sample src/.env     # Windows PowerShell
```

Then edit `src/.env` and set your real Apertus API key. The remaining values are
sensible defaults and can stay as-is:

```
APERTUS_BASE_URL=https://api.inference.cscs.ch/v1
APERTUS_API_KEY=<your-apertus-api-key>
APERTUS_MODEL=swiss-ai/Apertus-v1.5-70B
APERTUS_MODEL_LITE=swiss-ai/Apertus-v1.5-8B
APERTUS_MODEL_THINKING=swiss-ai/Apertus-v1.5-70B-thinking
MAX_TOKENS=5000
MAX_TOKENS_THINKING=100000
RPM=50
WAIT_MAX_SECONDS=4
STOP_AFTER_ATTEMPT_COUNT=3
STOP_AFTER_DELAY_SECONDS=15
```

| Variable | Meaning |
|---|---|
| `APERTUS_BASE_URL` | OpenAI-compatible inference endpoint. |
| `APERTUS_API_KEY` | Your API key. **Required.** |
| `APERTUS_MODEL` | Main chat / recipe model. |
| `APERTUS_MODEL_LITE` | Smaller/faster model for lightweight calls. |
| `APERTUS_MODEL_THINKING` | Reasoning model used for the chat summary. |
| `MAX_TOKENS` / `MAX_TOKENS_THINKING` | Output token ceilings. |
| `RPM` | Client-side rate limit (requests per minute). |
| `WAIT_MAX_SECONDS`, `STOP_AFTER_ATTEMPT_COUNT`, `STOP_AFTER_DELAY_SECONDS` | Retry/backoff tuning. |

> If you change `src/.env` after building, you must **rebuild** for the new values to
> take effect, because the file is copied into the image.

---

## 2. Build and run with `make`

From the `track_2b/` directory:

```bash
make run
```

This builds the Docker image and runs the container, attached to your terminal, with
port 7860 published. When you see:

```
* Running on local URL:  http://0.0.0.0:7860
```

open **http://localhost:7860** in your browser. From there, upload a photo of your
fridge/freezer/pantry (or add items by voice), review the detected inventory, then
generate recipes.

> **Voice input:** the browser asks permission to use the microphone the first time —
> click **Allow**. Browsers only grant mic access over a secure context, so open the app
> via `http://localhost:7860` (localhost counts as secure). Accessing it over `http://`
> with a LAN IP or hostname (e.g. `http://192.168.x.x:7860`) silently disables voice
> input — no prompt appears at all.

- Keep the terminal open — the container is attached to it.
- Press **Ctrl+C** to stop (the container is removed on exit).
- To force-stop a detached/leftover container:

  ```bash
  make stop
  ```

`make run` works whether you invoke it from inside `track_2b/` (`cd track_2b && make run`)
or from elsewhere (`make -C track_2b run`).

<details>
<summary>Example of a successful <code>make run</code> (fresh build — note the real timings)</summary>

```
william@DESKTOP-7KU25PQ:/mnt/c/project-template/track_2b$ make run
docker build -t aifridgechef src
[+] Building 121.8s (12/12) FINISHED                                                                     docker:default
 => [internal] load build definition from Dockerfile                                                               0.2s
 => => transferring dockerfile: 831B                                                                               0.1s
 => [internal] load metadata for docker.io/library/python:3.12-slim-bookworm                                       0.9s
 => [auth] library/python:pull token for registry-1.docker.io                                                      0.0s
 => [internal] load .dockerignore                                                                                  0.1s
 => => transferring context: 3.31kB                                                                                0.1s
 => [1/6] FROM docker.io/library/python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509  0.1s
 => => resolve docker.io/library/python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509  0.1s
 => [internal] load build context                                                                                 10.1s
 => => transferring context: 64.98kB                                                                              10.0s
 => CACHED [2/6] WORKDIR /app                                                                                      0.0s
 => CACHED [3/6] ADD requirements.txt .                                                                            0.0s
 => [4/6] RUN pip install --no-cache-dir -r requirements.txt                                                      75.4s
 => [5/6] COPY . .                                                                                                 1.0s
 => [6/6] RUN chgrp -R 0 /app     && chmod -R g=u /app                                                             4.8s
 => exporting to image                                                                                            28.8s
 => => exporting layers                                                                                           19.3s
 => => exporting manifest sha256:c5e3ddbd376fb720e66191bb26aed87ec7dfcaaad16f95f5c89f6d3737605341                  0.0s
 => => exporting config sha256:f8491480725031bf5b41984f73ec0301c2b2ca6dab795abe1ef12410d77aa763                    0.0s
 => => exporting attestation manifest sha256:fa01ede20acf9e0341753feae434d73421757d6424a77c12c79519b9772b4d9e      0.1s
 => => exporting manifest list sha256:71ea2b0dc679434b37232eb75e2d08389e546d4a5f1ec14411ae58b09c17bb81             0.0s
 => => naming to docker.io/library/aifridgechef:latest                                                             0.0s
 => => unpacking to docker.io/library/aifridgechef:latest                                                         10.2s
docker rm -f aifridgechef 2>/dev/null || true
docker run --rm --name aifridgechef -p 7860:7860 aifridgechef
13-Oct-26 08:24:54 [INFO] _client.py:1085 - HTTP Request: GET https://huggingface.co/api/agent-harnesses "HTTP/1.1 200 OK"
13-Oct-26 08:24:54 [INFO] _client.py:1085 - HTTP Request: HEAD https://huggingface.co/api/telemetry/https%3A/api.gradio.app/gradio-initiated-analytics "HTTP/1.1 200 OK"
* Running on local URL:  http://0.0.0.0:7860
13-Oct-26 08:24:54 [INFO] _client.py:1025 - HTTP Request: GET https://api.gradio.app/pkg-version "HTTP/1.1 200 OK"
13-Oct-26 08:24:54 [INFO] _client.py:1025 - HTTP Request: GET http://localhost:7860/gradio_api/startup-events "HTTP/1.1 200 OK"
13-Oct-26 08:24:54 [INFO] _client.py:1025 - HTTP Request: HEAD http://localhost:7860/ "HTTP/1.1 200 OK"
* To create a public link, set `share=True` in `launch()`.
13-Oct-26 08:24:54 [INFO] _client.py:1085 - HTTP Request: HEAD https://huggingface.co/api/telemetry/https%3A/api.gradio.app/gradio-launched-telemetry "HTTP/1.1 200 OK"
```

</details>

---

## Alternative: run with Docker directly

If `make` isn't available (or `make run` doesn't work in your environment), run the two
Docker commands yourself. From the `track_2b/` directory:

```bash
# Build the image (build context is the src/ directory, which holds the Dockerfile)
docker build -t aifridgechef src

# Run it, publishing the Gradio port
docker run --rm -p 7860:7860 aifridgechef
```

Then open **http://localhost:7860**. Press **Ctrl+C** to stop.

On Windows PowerShell the same commands work (adjust nothing but the shell):

```powershell
docker build -t aifridgechef src
docker run --rm -p 7860:7860 aifridgechef
```

To run detached and manage it by name:

```bash
docker run -d --name aifridgechef -p 7860:7860 aifridgechef
docker logs -f aifridgechef      # follow logs
docker rm -f aifridgechef        # stop & remove
```

---

## Apertus API usage

Every AI feature in this app runs on the **Apertus** model family via the CSCS inference
endpoint. The app deliberately uses three Apertus variants, matching each task to the
model whose capability and cost fit best — the small model for simple structured parsing,
the large instruct model for the heavier user-facing generation, and the reasoning model
only where multi-step reasoning is actually required.

| Model | Env var | Used for |
|---|---|---|
| **Apertus v1.5 8B** (lite) | `APERTUS_MODEL_LITE` | Lightweight structured parsing where a small, fast model is sufficient: parsing a photo-detected food list into the inventory, and applying a spoken inventory update (add/remove/adjust items). |
| **Apertus v1.5 70B** (instruct) | `APERTUS_MODEL` | The main user-facing generation and multimodal work: detecting foods in an uploaded fridge/freezer/pantry image, transcribing voice input, generating recipes tailored to the inventory + dietary restrictions + medical considerations, and the chef chat conversation. |
| **Apertus v1.5 70B thinking** (reasoning) | `APERTUS_MODEL_THINKING` | Reserved for the one task that needs genuine multi-step reasoning: the downloadable **chat summary**, which must group recipe variations and condense the conversation — a task the instruct model does not perform reliably. Given a larger output-token budget (`MAX_TOKENS_THINKING`) so the reasoning trace plus the final answer are not truncated. |

This split keeps the common, high-frequency operations cheap and fast on the 8B model,
spends the 70B instruct model on the quality-sensitive generation users see, and only
pays for the reasoning model on the single step that benefits from it.

### Multi-language support

The app leans directly on Apertus's multilingual capability to serve a Swiss audience in
its own languages. A **Recipe language** selector offers English plus the four Swiss
national languages:

- **English**
- **Deutsch** (German)
- **Français** (French)
- **Italiano** (Italian)
- **Rumantsch** (Romansh)

The chosen language is threaded through the prompts of the Apertus calls — recipe
generation, the chef chat, image food detection, and spoken inventory updates — so Apertus
produces its output (recipe names, ingredients, instructions, chat replies) **natively in
the selected language**, rather than generating in English and translating afterward. The
static template labels and section titles are localized to match, and the recipe/chat
prompts also apply Swiss-locale conventions for the four national languages (e.g. Swiss
German `ss` instead of `ß`, Swiss meal names like *souper*).

Voice input goes a step further: users can simply **speak in their native language** and
Apertus recognizes it automatically — no language needs to be selected. The
speech-to-text and spoken-inventory-update prompts instruct the model to preserve
whatever language is spoken, so Apertus detects the language from the audio and
transcribes/interprets it in that same language.

Romansh in particular is a strong demonstration of Apertus's reach — it is a low-resource
language most mainstream LLMs handle poorly, so including it means the app serves every
Swiss national language, not just the widely-spoken ones.

---

## Resource requirements

The app is lightweight at runtime because the heavy LLM inference runs **remotely** on
the Apertus endpoint — the container only runs the Gradio web server and orchestrates
API calls.

| | Recommendation |
|---|---|
| **CPU** | 1 core is enough to run; 2 cores gives comfortable headroom. |
| **Memory** | ~190 MB idle; **1–2 GB** recommended to absorb request spikes and image/audio handling. |
| **Disk** | Final image is roughly **1 GB** (~756 MB; Python 3.12-slim base + dependencies). Allow a few GB of free space for the build. |
| **Network** | Outbound HTTPS to `APERTUS_BASE_URL` (CSCS inference endpoint) is required at runtime. |
| **Port** | Publishes TCP **7860**. |

Observed footprint: an idle container sits around **~190 MB RAM** and near-zero CPU; CPU
and memory rise briefly during image detection, audio transcription, and recipe/summary
generation while requests are in flight.

**Build-time note:** the build installs Python dependencies with `pip`, which is the
slowest layer (~75s on a cold cache; a fresh build is roughly 2 minutes total, as in the
example above). A cached rebuild takes ~25s. The build itself can transiently use more
memory than the running app, so give Docker a reasonable memory allocation (on Docker
Desktop / WSL2, the default is usually fine).

---

## Project layout

```
track_2b/
├── Makefile          # `make run` builds the image and runs the container
├── README.md         # this file
└── src/              # application source + Docker build context
    ├── Dockerfile
    ├── .env_sample   # template; copy to .env and fill in
    ├── requirements.txt
    ├── gradio_ui.py  # app entry point (CMD in the Dockerfile)
    └── ...
```

---

## Troubleshooting

- **`ERROR: .../src/.env not found`** — you haven't created `src/.env` yet. Run the copy
  command in step 1 (in the `track_2b/` directory) and fill in your API key.
- **App starts but LLM calls fail / return auth errors** — a `403 Forbidden` from the
  inference endpoint means the API key is missing, wrong, or lacks access, e.g.:

  ```
  13-Oct-26 08:19:41 [INFO] _client.py:1923 - HTTP Request: POST https://api.inference.cscs.ch/v1/chat/completions "HTTP/1.1 403 Forbidden"
  ```

  Check `APERTUS_API_KEY` in `src/.env` is a real, valid key, then **rebuild** (the
  `.env` is baked into the image at build time, so editing it alone has no effect until
  you rebuild).
- **Port 7860 already in use** — stop whatever is using it, or map a different host port:
  `docker run --rm -p 8080:7860 aifridgechef` and open http://localhost:8080.
- **`make: command not found`** — use the direct Docker commands in the alternative
  section above.
- **(WSL) `cannot connect to the Docker daemon` / missing `/var/run/docker.sock`** —
  enable Docker Desktop → Settings → Resources → WSL integration for your distro, then
  Apply & Restart.
