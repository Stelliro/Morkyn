# Text to speech: read the story aloud

Mørkyn can read the narration aloud. One setting picks the backend: a **local engine** (Piper, runs on the CPU) or a **speech API** (any OpenAI-compatible `/v1/audio/speech` endpoint, or ElevenLabs). It is **off by default**; nothing is installed, downloaded or sent anywhere until you turn it on.

Code: `app/tts.py` (settings, presets, cleaning, the three providers, install), the `/api/tts-*` routes in `app/main.py`, the Play bar and the Speech settings form in `static/app.js`, the right-click items in `static/ui/interact.js`. Tests: `python -m unittest tests.test_tts`, `node tools/test_tts_ui.js`.

## What it does

- Speaks the **shipped narration text** only. `[[L1]]`-style codes, bare `L1` / `I2` codes, HTML, markdown marks, URLs, op lines and debug lines are removed before anything is synthesised. The browser cleans the text first; the server cleans it again.
- Reads **paragraph by paragraph**. Each paragraph is one request, so playback starts as soon as the first paragraph is ready while the next one is being made.
- **Never runs at the same time as the model.** Playback stops the moment you send a turn, Continue, Wait, Regenerate or Rewind, or go back to the main menu. On the server, local synthesis takes the GPU gate and answers "busy" instead of queueing while a turn or an image job holds it.
- Speed, voice and provider are settings. The speed you set is applied by the backend where it can be (Piper and OpenAI take any speed; ElevenLabs accepts 0.7 to 1.2) and the browser's playback rate makes up the rest, so the result is the speed you asked for.

## Where the settings are

- **Main menu → Settings.** The Speech section sits under the launcher settings. It saves on its own (to `/api/tts-config`, not to the launcher prefs).
- **In game:** open the play menu (the menu button in the top bar) and pick **Speech**. It opens the same form in a dialog.

The form: **Provider**, **Read narration aloud** (the on/off switch), **Voice** (Piper) or **Preset** plus **Voice** (APIs, with a **Custom…** entry for a voice id that is not in the list), **Model** and **Base URL** (APIs), **API key** (password field; when a key is saved the placeholder reads `Saved (••••1234). Leave blank to keep.`), **Speed** (0.5× to 2×), and under **More**: **Characters per request** (0 = the preset's default) and **Timeout**. Buttons: **Save**, **Test** (probes the backend, no synthesis, no cost) and, for Piper, **Install local speech engine**.

Speech is on only when the provider is not **Off** *and* **Read narration aloud** is ticked. Until both are true there is no Play bar and no menu item, so an unused feature leaves no trace in the play view.

## Turning it on

### Local (Piper)

Piper runs on the CPU. A voice is a pair of files (about 63 MB for a medium voice, 115 MB for the high one) that lands in `data/tts-voices/` (gitignored). The engine itself is the `piper-tts` package from PyPI; it is **not** part of `requirements.txt`, so the game installs it only when you ask.

1. Open the Speech settings. Set **Provider** to **Local (Piper, runs on the CPU)**.
2. Pick a **Voice** from the list (the default is `en_US-lessac-medium`). Tick **Read narration aloud**.
3. Press **Install local speech engine**. The form saves first, then runs `python -m pip install piper-tts==1.8.0` in the game's own Python and downloads the chosen voice. The status line says what it is doing; this can take a few minutes the first time. When it is done the status line lists both steps, for example `Engine: installed (piper-tts 1.8.0) · Voice: installed (en_US-lessac-medium (63.1 MB))`, followed by the probe's `Ready:` sentence naming the provider and the voice.
4. Press **Test** any time to see the same `Ready:` line, or what is still missing.
5. Play a turn. A **Play** button appears under the narration.

If you later pick another voice and press Play without installing, the game downloads that voice by itself on the first Play (the bar says `Downloading the voice en_GB-alba-medium… this can take a minute.`). Only the engine needs the Install button.

The voice folder can be moved with `AI_RPG_TTS_VOICE_DIR=<path>` (a relative path is taken from the Mørkyn folder, not from where the server was started). The form shows the folder in use under the buttons.

### OpenAI-compatible API

Works with OpenAI's speech endpoint and with any server that speaks the same protocol (`POST {base_url}/v1/audio/speech` with `model`, `input`, `voice`, `speed`, `response_format`), for example a local Kokoro-FastAPI server.

1. Set **Provider** to **OpenAI-compatible API**.
2. Pick a **Preset**: `OpenAI · gpt-4o-mini-tts` (default), `OpenAI · tts-1`, or `Custom OpenAI-compatible URL` for your own server.
3. Pick a **Voice** (nine names for the OpenAI presets; free text for a custom server). Change **Model** or **Base URL** only if your server needs it. The base URL is entered **without** `/v1`; a pasted `/v1` is stripped.
4. Enter the **API key** in the form, or leave the field blank and set it in the environment: `AI_RPG_TTS_API_KEY`, or `OPENAI_API_KEY`. A server on `127.0.0.1` / `localhost` needs no key.
5. Tick **Read narration aloud**, press **Save**, then **Test**. `Ready: OpenAI-compatible API, gpt-4o-mini-tts, voice coral.` means the server answered.

### ElevenLabs

1. Set **Provider** to **ElevenLabs**.
2. Pick a **Preset** (`Multilingual v2` for quality, `Turbo v2.5` or `Flash v2.5` for speed) and a **Voice** (five well-known default voices, or **Custom…** and a voice id from your own account).
3. Enter the **API key** in the form or set `AI_RPG_TTS_API_KEY`, `ELEVENLABS_API_KEY` or `ELEVEN_API_KEY` in the environment.
4. Tick **Read narration aloud**, **Save**, **Test**. `ElevenLabs refused the API key.` means the key is wrong.

### Keys: where they live and where they go

- Order of use: the key saved in the form, then `AI_RPG_TTS_API_KEY`, then the provider's usual variable (`OPENAI_API_KEY`, or `ELEVENLABS_API_KEY` / `ELEVEN_API_KEY`).
- A saved key is never sent back to the browser. `GET /api/tts-config` returns `api_key: ""` with `api_key_set: true` and a four-character hint; the game state blanks it too; a world **Export** has it removed. Leaving the field blank on Save keeps the saved key.
- When a cloud provider is on, the **paragraph text** you play is sent to that service. Piper sends nothing anywhere; its install reaches PyPI once and each voice download reaches Hugging Face once.

## Presets

Every preset carries working settings (voice, model, sample rate, speed range, characters per request). Blank fields in the form mean "from the preset"; `GET /api/tts-config` shows what will really be used under `resolved`.

### Piper voices (local, 22050 Hz wav, 600 characters a request)

| Voice | Speaker | Quality | Size |
| --- | --- | --- | ---: |
| `en_US-lessac-medium` (default) | English (US), female | medium | ~63 MB |
| `en_US-amy-medium` | English (US), female | medium | ~63 MB |
| `en_US-ryan-high` | English (US), male | high | ~115 MB |
| `en_US-joe-medium` | English (US), male | medium | ~63 MB |
| `en_GB-alan-medium` | English (UK), male | medium | ~63 MB |
| `en_GB-alba-medium` | English (UK), female | medium | ~63 MB |

Files come from `rhasspy/piper-voices` on Hugging Face; each voice folder has a `MODEL_CARD` with that voice's licence. Speed 0.5 to 2.0 is applied as Piper's `length_scale = 1 / speed`.

### OpenAI-compatible (mp3, 24000 Hz)

| Preset | Base URL | Model | Default voice | Characters a request | Key |
| --- | --- | --- | --- | ---: | --- |
| `OpenAI · gpt-4o-mini-tts` (default) | `https://api.openai.com` | `gpt-4o-mini-tts` | `coral` | 4000 | `OPENAI_API_KEY` |
| `OpenAI · tts-1` | `https://api.openai.com` | `tts-1` | `onyx` | 4000 | `OPENAI_API_KEY` |
| `Custom OpenAI-compatible URL` | `http://127.0.0.1:8880` | `tts-1` | free text | 1000 | `AI_RPG_TTS_API_KEY` (none needed on loopback) |

Voices for the OpenAI presets: alloy, ash, coral, echo, fable, onyx, nova, sage, shimmer. Any other voice name the server accepts can be typed under **Custom…**. Speed 0.5 to 2.0 is sent as the request's `speed`. `8880` is only a placeholder port (a common one for local servers that speak this protocol).

### ElevenLabs (mp3, `mp3_44100_128`, 4000 characters a request)

| Preset | Model |
| --- | --- |
| `ElevenLabs · Multilingual v2 (quality)` (default) | `eleven_multilingual_v2` |
| `ElevenLabs · Turbo v2.5 (fast)` | `eleven_turbo_v2_5` |
| `ElevenLabs · Flash v2.5 (fastest)` | `eleven_flash_v2_5` |

Default voice Rachel (`21m00Tcm4TlvDq8ikWAM`); also listed: Adam, Bella, Antoni, George. Any voice id from your account can be typed under **Custom…**. ElevenLabs accepts a speed of 0.7 to 1.2 (`voice_settings.speed`); a faster or slower setting is clamped there and the browser's playback rate covers the rest.

### Changing provider or preset

Switching the provider or the preset starts from that preset's own voice, model and URL; the form shows this at once, and Save stores it the same way. A voice id therefore never carries over from one service to another. Going back to the saved preset shows the saved values again. The key field is kept while you switch.

## Controls

### The Play bar

When speech is on, one small bar sits **directly under the turn's narration**, above rewards, rolls and the Debug row:

- **Play** reads the whole turn, paragraph by paragraph. While it reads, the button says **Pause**; paused, it says **Resume**.
- **Stop** appears while something is playing or paused and clears the queue.
- A status to the right: `Synthesizing…`, `Paragraph 2 of 6`, `Stopped.`, or an error sentence. Errors are text on the bar, never a pop-up.

There are no per-paragraph buttons in the prose (user decision: they clutter it). The bar is rebuilt after every narration render and is not shown while the narration is still being typed out.

### Right-click in the narration

- **Select some text** inside the narration and right-click: **Play selected text**.
- Right-click **inside a paragraph with nothing selected**: **Play this paragraph**.
- While something plays: **Stop**.
- Right-click on a **name** still opens that name's own menu (Talk, Ask, …) with the read-aloud items added at the end of it.

Outside the narration, or while speech is off, the browser's normal menu appears as before.

### The never-at-the-same-time rule

The player listens, then decides. Sending a turn, **Continue**, **Wait**, **Regenerate** or **Rewind** stops playback and drops any paragraph still being made; so does leaving to the main menu. On the server, Piper synthesis takes the same GPU gate the story model and the image engine use: a request that arrives while a turn or an image job holds it is answered with **409** and the sentence `The model or the image engine is using the GPU right now. Wait for the turn to finish, then press Play again.` The browser stops the queue and keeps the Play button, so you press Play once the turn has landed. Cloud providers do not take the gate; they do not use the GPU. Piper is CPU-only today, but the gate stays so a future GPU engine inherits the rule.

The browser keeps **one speech request in flight**: the next paragraph is fetched only after the current one has started playing. A paragraph that cannot be read (empty after cleaning, or too long) is skipped with a note on the bar and the reading continues after a second.

## Settings reference

Stored as one settings row `tts_config`. An environment variable wins over the saved value when it is set.

| Field | Env | Default | Notes |
| --- | --- | --- | --- |
| `provider` | `AI_RPG_TTS_PROVIDER` | `off` | `off`, `piper`, `openai`, `elevenlabs` (`local`, `custom`, `eleven` and a few other aliases are accepted) |
| `enabled` | `AI_RPG_TTS_ENABLED` | `0` | Speech is active only when this is on **and** the provider is not `off` |
| `preset` | `AI_RPG_TTS_PRESET` | `""` | A preset id of the current provider; blank = the provider's default |
| `voice` | `AI_RPG_TTS_VOICE` | `""` | Piper voice code, OpenAI voice name, or ElevenLabs voice id; blank = from the preset |
| `model` | `AI_RPG_TTS_MODEL` | `""` | API model (`gpt-4o-mini-tts`, `eleven_turbo_v2_5`, …); Piper ignores it |
| `base_url` | `AI_RPG_TTS_BASE_URL` | `""` | OpenAI-compatible only, without `/v1` |
| `api_key` | `AI_RPG_TTS_API_KEY` | `""` | Falls back to `OPENAI_API_KEY` or `ELEVENLABS_API_KEY` / `ELEVEN_API_KEY` |
| `speed` | `AI_RPG_TTS_SPEED` | `1.0` | 0.5 to 2.0 |
| `chunk_chars` | `AI_RPG_TTS_CHUNK_CHARS` | `0` | Characters per request; 0 = the preset's value, otherwise 200 to 4000 |
| `timeout_seconds` | `AI_RPG_TTS_TIMEOUT` | `60` | Per request, 5 to 300 |
| (not stored) | `AI_RPG_TTS_VOICE_DIR` | `data/tts-voices` | Where Piper voices are kept |

The same names are listed, commented out, in `.env.example`.

## Routes

| Route | What |
| --- | --- |
| `GET /api/tts-config` | The settings with the key masked, plus `active`, `resolved` and `voice_dir` |
| `POST /api/tts-config` | Partial update; a blank `api_key` keeps the saved one |
| `GET /api/tts-catalog` | The presets above, with every default |
| `POST /api/tts-status` | The probe behind **Test**; never fails, `detail` says what is missing |
| `POST /api/tts/speak` | `{text, voice?, speed?}` for one paragraph (up to 4000 characters) → `audio/wav` (Piper) or `audio/mpeg` (APIs); 400 off / empty / not ready, 409 GPU busy, 503 backend unreachable |
| `POST /api/tts/install` | `{what: all / engine / voice}`; the Install button sends `all`, the first Play of a missing voice sends `voice` |

## Why Piper ships (and Kokoro and XTTS-v2 do not)

Three local engines were evaluated against the rule that speech must not fight the story model for a 12 GB card, and that an optional feature must stay small:

| | Piper (`piper-tts` 1.8.0) | Kokoro-82M | XTTS-v2 (Coqui) |
| --- | --- | --- | --- |
| Quality | Clear, natural enough for narration; per-voice; no emotion control | Better prosody than Piper, among the best small models | Best of the three, voice cloning, emotional range |
| Speed on a 12 GB GPU | CPU-only path used; GPU not needed | Real-time or better on the GPU; roughly real-time on the CPU with the ONNX build | Real-time only on the GPU (2–4 GB VRAM), which the 8B story model already occupies on a 12 GB card |
| Speed on CPU | Faster than real time on a laptop core (a medium voice makes a paragraph in about a second) | Near real-time on a modern CPU, slower on older ones | Several times slower than real time; not usable |
| Licence | Package: GPL-3.0-or-later (`piper1-gpl`; bundles espeak-ng); voices: per-voice `MODEL_CARD` on Hugging Face (most permissive) | Weights Apache-2.0; needs espeak-ng (GPL) and the `kokoro` / `misaki` packages | Coqui Public Model Licence (non-commercial); the `TTS` package is MPL-2.0 |
| Install size | About 110 MB of wheels (46 MB piper with espeak data, 61 MB onnxruntime) plus 63–115 MB per voice | 2–3 GB (torch and CUDA libraries), or about 400 MB by the ONNX route plus a 330 MB model | About 1.8 GB model plus torch (2–3 GB) |

Piper ships because it is the only candidate that reads the story on the CPU faster than the player can listen, so it never asks the graphics card for memory the story model is using, and because a voice is one 60–115 MB file pair that downloads on first use the way the story model does. Kokoro sounds better but drags in torch or a second runtime and a multi-gigabyte install for a feature that is off by default. XTTS-v2 sounds best but needs the GPU to be real-time and its model licence forbids commercial use, so it would both fight the narrator for VRAM and constrain the project.

**Licence note.** The `piper-tts` 1.8.0 wheel on PyPI is the `piper1-gpl` line and is **GPL-3.0-or-later** (it links the GPL espeak-ng phonemiser); the original `rhasspy/piper` C++ project is MIT. Mørkyn does not bundle or import the package at install time and it is not in `requirements.txt`: the player installs it on demand from the UI as a separate program, and the game imports it only once it is there. Each voice has its own licence in its `MODEL_CARD`.

Cloud presets were chosen the same way: OpenAI's two speech models and the plain `/v1/audio/speech` protocol (so a local server such as Kokoro-FastAPI works too), and ElevenLabs' three current models with a handful of its default voices.

## Troubleshooting

Every error is one plain sentence, shown on the Play bar or under the settings form.

| What you see | What it means | What to do |
| --- | --- | --- |
| `Speech is off. Turn it on in Speech settings.` | The provider is Off, or **Read narration aloud** is not ticked | Set a provider, tick the box, Save |
| `The local speech engine is not installed. Open Speech settings and press Install.` | Piper is chosen but the `piper-tts` package is not in the game's Python | Press **Install local speech engine**. It needs PyPI to be reachable. If pip finishes but the import still fails, restart the server |
| `Could not install the speech engine: <pip output>` (503) | pip failed; the last lines of its output follow | Read the pip text; check the network and disk space; try again (a second press is safe) |
| `The voice en_US-lessac-medium is not downloaded yet. Open Speech settings and press Install.` | The engine is there, the voice files are not | Press Play once (it downloads the voice by itself) or press Install |
| `Could not download the voice …: <reason>` (503) | Hugging Face did not answer, or the files were not a Piper voice | Check that `huggingface.co` is reachable from this machine (a proxy that blocks it gives HTTP 403); partial files are removed, so just try again |
| `Unknown voice "…". Pick one from the list in Speech settings.` | A voice code that is not in the catalog and not on disk | Pick a listed voice |
| `The model or the image engine is using the GPU right now. Wait for the turn to finish, then press Play again.` (409) | A turn or an image job holds the GPU gate | Wait for the turn to land, then press Play |
| `The local speech engine is still busy with the previous paragraph. Press Play again.` (503) | An earlier speech request (another tab, or one just stopped) kept the engine past the timeout | Press Play again |
| `No API key for the speech service. Enter one in Speech settings or set AI_RPG_TTS_API_KEY or OPENAI_API_KEY.` | Cloud provider, no key anywhere, and the host is not loopback | Enter a key in the form or set the variable; a local server on `127.0.0.1` needs none |
| `The speech service refused the request (HTTP 401): …` (503), or **Test** says `… refused the API key.` | The service rejected the key | Check the key and the account |
| `The speech service refused the request (HTTP 4xx/5xx): …` (503) | The service answered with an error; the first 200 characters of its body follow | Read the body: wrong model or voice name, quota, or a server-side fault |
| `The speech service did not answer: <reason>` (503) | Network error or timeout | Check the base URL (no `/v1`), that the server is running, and the **Timeout** under More |
| `Nothing to read: the text is empty once codes and markup are removed.` | The selection or paragraph was only codes or markup | Select prose |
| `Paragraph 3 could not be read: …` on the bar | One paragraph was skipped (empty or longer than the route accepts); the reading went on | Nothing to do |
| `The browser could not play the audio it received.` | The browser rejected the audio data | For a custom server, check that it returns real mp3 for `response_format: mp3` |
| The Play bar is missing | Speech is off, the narration is still being typed out, or there is no narration on screen | Turn speech on; wait for the reveal to finish |

Playback is per browser tab; the server only makes audio. Nothing about speech is stored in a save, a rewind or a campaign slot except the settings row itself, which is an app setting like the model and image settings.
