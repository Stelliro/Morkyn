# Connecting APIs and agents to Mørkyn

Mørkyn can run on:

| Provider | Best for |
| --- | --- |
| `ollama` | Local models via Ollama |
| `llama_cpp` | Local GGUF + managed llama.cpp server |
| `openai` | **Cloud / agents** — any OpenAI-compatible Chat Completions API |

## Quick: xAI Grok (recommended cloud)

1. Create a key at https://console.x.ai  
2. Put it in a git-ignored `.env` (copy from `.env.example`):

```env
AI_RPG_MODEL_PROVIDER=openai
AI_RPG_API_PRESET=xai
AI_RPG_API_BASE_URL=https://api.x.ai/v1
AI_RPG_API_MODEL=grok-4.5
XAI_API_KEY=xai-...
```

3. Or set the same fields under **LLM Settings** in the UI (provider = *Cloud / agent API*).  
   Leave the password field blank on later saves to keep an existing key.

4. **Test Connection** should list models or accept the configured model.

Aliases accepted for provider: `openai`, `xai`, `grok`, `spacexai`, `api`, `openai_compat`.

## Other OpenAI-compatible endpoints

| Service | Base URL | Key env |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| OpenRouter | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` or `AI_RPG_API_KEY` |
| LiteLLM / custom proxy | `http://127.0.0.1:4000/v1` | `AI_RPG_API_KEY` |
| Local agent gateway | your `/v1` URL | optional |

Mørkyn calls:

```http
POST {api_base_url}/v1/chat/completions
Authorization: Bearer {api_key}
```

with standard `messages` (system + user). No browser-side key exposure.

## Agent bridge (external tools / Grok-like agents)

With the app running (e.g. `http://127.0.0.1:8000`):

| Endpoint | Purpose |
| --- | --- |
| `GET /api/agent/health` | Bridge status + provider |
| `GET /api/agent/state?token=` | Full play state JSON |
| `POST /api/agent/turn` | Submit a player action |
| `POST /api/agent/opening?token=` | Fire opening scene |

### Auth

- If `AI_RPG_AGENT_TOKEN` is **unset/empty**, endpoints are open (local trust).  
- If set, pass `token` query param or JSON field `token`.

### Example: play a turn as an external agent

```powershell
$body = @{ text = "I look around the gate carefully."; token = $env:AI_RPG_AGENT_TOKEN } | ConvertTo-Json
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/api/agent/turn" `
  -ContentType "application/json" -Body $body
```

```bash
curl -s http://127.0.0.1:8000/api/agent/turn \
  -H "Content-Type: application/json" \
  -d '{"text":"I ask the merchant about bandits."}'
```

The GM still runs through Mørkyn’s normal turn pipeline (DSL/JSON, optional narration pipeline, `apply_turn`). Your agent only supplies **player** text (or drives setup via existing `/api/*` routes).

## Launcher

Simple menu **[3] Change engine** cycles:

`ollama` → `llama_cpp` → `openai` (cloud)

Advanced Gatehouse **[B] Provider** does the same. Cloud keys still come from env or LLM Settings.

## Security notes

- Prefer env vars over storing keys in SQLite.  
- GET `/api/model-config` never returns raw keys (`api_key_set` + hint only).  
- Empty `api_key` on save keeps the previous key.  
- Do not commit `.env`.