# Local image backends (Forge / ComfyUI)

Mørkyn can optionally call a **local** image server for portraits (and later map art).  
Nothing runs until you set a provider — default is **off**.

## Supported

| Provider | Typical URL | API used |
| --- | --- | --- |
| **Off** | — | — |
| **Forge / A1111** | `http://127.0.0.1:7860` | `POST /sdapi/v1/txt2img` |
| **ComfyUI** | `http://127.0.0.1:8188` | `POST /prompt` + `GET /history/{id}` + `/view` |

Forge and Automatic1111 both expose the same **sdapi** surface when started with API enabled.

## Quick setup

### Forge / A1111

1. Launch Forge (or A1111) with API on (Forge usually enables it; A1111 may need `--api`).
2. In Mørkyn → **LLM Settings** → **Image backend**:
   - Provider: **Forge / A1111**
   - URL: `http://127.0.0.1:7860`
3. **Test image backend**, then **Save**.
4. On setup → Character → **Preview** (portrait).

### ComfyUI

1. Run ComfyUI (default port **8188**).
2. Note a checkpoint filename that exists in your Comfy `models/checkpoints` folder.
3. In Mørkyn image settings:
   - Provider: **ComfyUI**
   - URL: `http://127.0.0.1:8188`
   - Checkpoint: e.g. `v1-5-pruned-emaonly.safetensors` (must match your disk)
   - Workflow: `txt2img_api.json` (default under `app/comfy_workflows/`)
4. Test + Save + Portrait Preview.

## Custom Comfy workflow

Export a workflow in **API format** from ComfyUI and save it as:

```text
app/comfy_workflows/your_workflow.json
```

Then set **Comfy workflow** to `your_workflow.json`.

Mørkyn will try to inject:

- first `CLIPTextEncode` → positive prompt  
- second `CLIPTextEncode` → negative  
- `EmptyLatentImage` width/height  
- `KSampler` seed/steps/cfg  
- `CheckpointLoaderSimple` if you set a checkpoint  

You can also use placeholders in the JSON strings:

`{{PROMPT}}` `{{NEGATIVE}}` `{{WIDTH}}` `{{HEIGHT}}` `{{STEPS}}` `{{CFG}}` `{{SEED}}` `{{CHECKPOINT}}`

## Environment overrides

```powershell
$env:AI_RPG_IMAGE_PROVIDER = "forge"   # off | forge | comfyui
$env:AI_RPG_FORGE_URL = "http://127.0.0.1:7860"
$env:AI_RPG_COMFY_URL = "http://127.0.0.1:8188"
$env:AI_RPG_COMFY_CHECKPOINT = "your-model.safetensors"
$env:AI_RPG_COMFY_WORKFLOW = "txt2img_api.json"
$env:AI_RPG_IMAGE_WIDTH = "512"
$env:AI_RPG_IMAGE_HEIGHT = "512"
$env:AI_RPG_IMAGE_STEPS = "20"
$env:AI_RPG_PORTRAIT_STYLE = "pixel art portrait, 8-bit style, bust"
```

## API

```text
GET  /api/image-config
POST /api/image-config
POST /api/image-status          # probe backend
POST /api/image/generate        # { prompt, purpose?, width?, height?, ... }
POST /api/image/portrait        # builds prompt from name/title/backstory
```

Generated files (when successful) land under `data/portraits/` (gitignored via `data/`).

## Why not force one stack?

- **Forge/A1111** is the simplest for most users (one txt2img call).  
- **ComfyUI** is better if you already have a custom pixel-art graph — drop in a workflow JSON.  
- Keeping this **optional and local** matches Mørkyn’s privacy model.
