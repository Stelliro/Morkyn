# Local image backends (Forge / ComfyUI)

Mørkyn can optionally call a **local** image server for portraits (and later map art).  
Nothing runs until you set a provider — default is **off**.

## Verification status

| Backend | Status |
| --- | --- |
| **Forge / ForgeSD** | **Primary / tested** — use this for character art today. |
| **ComfyUI** | **Not fully verified** — settings, roots, launch helpers, and a default workflow inject exist, but the project owner has not finished end-to-end Comfy validation yet (focus is ForgeSD). Once verified by the owner or a contributor, this note will be cleared in the README and here. |

Repos:

- Forge: https://github.com/lllyasviel/stable-diffusion-webui-forge  
- ComfyUI: https://github.com/comfyanonymous/ComfyUI  

## Supported

| Provider | Typical URL | API used |
| --- | --- | --- |
| **Off** | — | — |
| **Forge / A1111** | `http://127.0.0.1:7860` | `POST /sdapi/v1/txt2img` |
| **ComfyUI** | `http://127.0.0.1:8188` | `POST /prompt` + `GET /history/{id}` + `/view` |

Forge and Automatic1111 both expose the same **sdapi** surface when started with API enabled.

## Installs tab (face lock extras)

**LLM Settings → Images → Installs** lists path-aware packages:

- Forge root presence, ControlNet folder, InstantID weights (Hugging Face InstantX/InstantID), FaceID adapters, InsightFace wheel into Forge’s Python  
- Comfy root presence, `ComfyUI_IPAdapter_plus`, `ComfyUI_InstantID` (git clone into `custom_nodes`)

Rules:

1. Set **Forge install root** and/or **Comfy install root** and **Save** first.  
   - **Browse…** opens a native folder picker (any folder you choose).  
   - **Allow search** scans common locations (optional).  
   - Or paste a path by hand.  
2. Until that root is set, every Install button for that backend is **blocked**.  
3. If files/nodes already exist on disk, the row shows **Installed**.  
4. Large ControlNet downloads can take several minutes.

API: `GET /api/image-installables`, `POST /api/image-installables/install` with `{ "id": "forge_instantid_ipadapter" }`, `POST /api/select-folder` for the folder picker.

## Character art (face + full body)

One **Generate both** button (setup Identity or play Player tab) runs:

1. Face bust (small chip on Player)  
2. Full-body standing figure  

Presets live in **`data/image_presets.json`** (defaults: `config/image_presets.default.json`).  
Edit sizes/steps/styles without code changes.

## Quick setup

### Forge / A1111

**Prefer a Forge portable pack** (e.g. `D:\ForgeSD`) that ships **Python 3.10.6**.  
Stock AUTOMATIC1111 on system Python **3.14 will fail** installing `torch==2.1.2` — that is a Python version problem, not Morkyn.

**Morkyn does not modify your Forge/Comfy install.** Launch uses Morkyn-owned scripts only:

- `tools/morkyn_forge_api.bat` — sets `--api --nowebui` and optional `--ckpt-dir` in the **process environment**, then calls the install’s `webui.bat`  
- `tools/morkyn_comfy_api.bat` — same idea for Comfy  

Your `webui-user.bat` / Gradio preferences stay as you set them for normal use.

1. Install / update Forge yourself (`update.bat` / git pull).  
2. In Morkyn, set **Forge root** to the pack (e.g. `D:\ForgeSD`) → **Launch backend** (headless API).  
3. Checkpoints: scanned from disk + API; generation uses the selected checkpoint name.  
3. In Mørkyn → **LLM Settings** → **Images** (three tabs):
   - **General** — active provider, shared defaults, auto-launch  
   - **Forge / A1111** — URL `http://127.0.0.1:7860`, install root = pack root (`D:\ForgeSD`) or `…\webui`  
   - **ComfyUI** — URL, root, checkpoint, workflow, sampler, scheduler  
4. Start Forge, then **Refresh catalog** to pull live models/samplers into dropdowns.  
5. **Test connection** / **Check readiness**, then **Save**.  
6. Setup → Identity → **Generate both**, or in play → Player → **Generate both**.

**If you see `Couldn't install torch` / Python 3.14:** stop using that WebUI venv. Point Morkyn at Forge with bundled 3.10, or install Python 3.10.6 and recreate the venv — do not chase torch wheels on 3.14 for classic A1111.

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
POST /api/image-status              # probe backend
GET/POST /api/image-readiness       # checklist + optional launch wait
GET/POST /api/image-catalog         # live models/samplers/VAEs/workflows
POST /api/image-path-search         # { kind: "forge"|"comfyui" } consented scan
POST /api/image-launch              # start from install root
GET/POST /api/image-presets         # face/fullbody cfg file
POST /api/image/character-set       # face + fullbody dual gen
POST /api/image/generate            # raw prompt
POST /api/image/portrait            # legacy single bust
```

### Settings applied on generate

| Backend | Applied from Mørkyn config |
|---------|----------------------------|
| Forge | checkpoint, VAE, sampler, scheduler, CLIP skip, restore faces, tiling, hires fix (scale/upscaler/denoising) via `txt2img` + `override_settings` |
| Comfy | checkpoint, workflow JSON, sampler_name, scheduler injected into KSampler / CheckpointLoader nodes |

Generated files land under `data/portraits/` (gitignored via `data/`).

## Why not force one stack?

- **Forge/A1111** is the simplest for most users (one txt2img call).  
- **ComfyUI** is better if you already have a custom pixel-art graph — drop in a workflow JSON.  
- Keeping this **optional and local** matches Mørkyn’s privacy model.
