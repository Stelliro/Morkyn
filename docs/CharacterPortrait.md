# Character art (face + full body)

Status: **shipped** (local Forge / ComfyUI). Optional — provider default is **off** until set.

## What you get

| Asset | Role | Storage |
|-------|------|---------|
| **Face** | Small circular chip on Player tab; source for map head | `settings.player_portrait` |
| **Full body** | Taller **3:4** frame (default 576×768) | `settings.player_fullbody` |
| **Map head** | Circle-cropped face token; ring drawn by map UI (not in the PNG) | `settings.map_avatar` |

## Generate controls

### Setup → Identity → Character art

- Card **starts collapsed**. Expand the header to generate; **Set or install ForgeSD** opens **LLM Settings → Images → Installs**.
- **Extra prompt** / optional **negative** / **LoRAs** / **checkpoint**
- **Face** · **Body** tabs (generate the selected image only)
- **Full body uses face as reference** (face is **composited** into the top of a tall canvas, then img2img — not stretched full-frame, which used to force bust/portrait crops)
- **Studio…** opens the **Image Studio** popout
- Image settings are tabbed: **General** · **Forge** · **ComfyUI** (unverified) · **Installs**

### Play → Player

- Face / Body / Both + Studio…

### Backend connect policy

1. **Discover / hook** live API (including nearby ports e.g. 7861 if 7860 is busy)  
2. If API ok → generate  
3. If a Forge process/port is loading → wait, **do not** open a second window  
4. If truly offline and install root is set → **one** launch, then poll  

## Prompt layers

| Layer | Meaning |
|-------|---------|
| **A. Primary** | Game-wide style (Image Studio → Save primary prompts) |
| **B. Subject** | Identity / visibility / gear (auto) |
| **C. Extra** | Setup/studio one-shot + LoRA tags |

Final prompt ≈ `A + B + C` + `<lora:name:weight>`.

### Face vs clothes (player setup)

| Field | Role in prompts |
|-------|------------------|
| **Hair** | Length / color / style (`short brown hair`) — always bust-visible |
| **Facial features** | Eyes, freckles, scars, jaw — face + full body anchors |
| **Clothing / look** (`appearance`) | Zone-tagged clothes only |
| **Starter equipment** | Inventory + wearable art cues by zone |

Prompt order: subject → setting → pose → **hair** → **facial features** → **zone-filtered clothes** → framing.

### Wardrobe zones (player + NPC)

Clothes / starter gear / observed NPC look are parsed into **category + body zone**, then filtered by image frame so bust crops never mention boots.

| Frame | Zones allowed |
|-------|----------------|
| **Face / partial** | hair, head, face, neck, torso |
| **Full body** | those + arms, hands, waist, legs, feet, bag, held |

Preferred clothing text:

```text
torso: travel-stained coat; feet: dusty boots
```

Free words still work (`worn coat, dusty boots`) — zones are inferred. Consumables/coins are skipped for art. NPC portraits use `appearance` / `observed_description` through the same wardrobe filter (plus any hair/face words present in that text).

## Image Studio popout

- Edit **primary positive/negative**
- Generate face/body/both (shared GPU queue)
- **Candidates** library with **Use face** / **Use body**
- Catalog refresh for checkpoints + LoRAs

## Presets cfg

| File | Purpose |
|------|---------|
| `config/image_presets.default.json` | Shipped defaults (fullbody 576×768) |
| `data/image_presets.json` | User copy |

## API (summary)

```text
POST /api/image/character-set
  { kinds: ["face"|"fullbody"], extra, loras: [{name, weight}],
    use_face_reference, reference_data_url, launch_if_offline, … }
POST /api/image-catalog   → includes forge.loras when API is up
GET/POST /api/image-config  → primary_prompt, primary_negative, fullbody_ref_denoise
```

## Character consistency (face lock)

Setting: **LLM Settings → Images → Face lock** (default **Light**).

| Mode | Behavior | Expectation |
|------|----------|-------------|
| **light** (recommended) | img2img from the other image (face ↔ body) | Works on most GPUs with Forge API; slightly more VRAM/time |
| **auto** | Light, or Strong only if a *safe* ControlNet face model is API-registered | Usually Light on current Forge builds |
| **strong** (experimental) | ControlNet face when available; **falls back to Light** on errors | Can OOM/crash weaker cards; InstantID via API is unreliable |
| **off** | No cross-image ref | Fastest; face and body may drift |

Also: **Light ref strength (denoise)** — higher = freer pose / weaker match; lower = stronger face match.

**Warning in UI:** if your PC can’t handle the extra pass, use Light or Off, lower steps/size, close other GPU apps.

### ADetailer (optional)

Also under **Images → Face lock**: enable **ADetailer** for a post-gen face detect + inpaint pass (sharper faces).

- Requires the `adetailer` extension in Forge (listed in scripts as `adetailer`).
- Extra GPU time/VRAM — can OOM weak cards; start with face-only and denoise ~0.4.
- On extension errors, Mørkyn retries the gen once without ADetailer.

**Use face as reference** (default on when ADetailer is enabled):

Stock ADetailer has **no API field for an external reference face**. Mørkyn approximates the workflow you want:

1. If a face image already exists and this option is on, the **main gen uses light face lock** (img2img from that face) even if global face-lock mode is Off — so the canvas already carries the right identity.  
2. ADetailer then **detects and re-details that face** with identity-aware settings (face-focused prompt tags, slightly gentler denoise, softer mask blur).  
3. Workflow: generate **Face** first → then **Full body** with ADetailer + “Use face as reference”.

This is “lock then detail,” not a separate ADetailer-only ref slot.

**Test face-lock** probes capability: `POST /api/image/character-lock-test`

## Limits

- Strong lock needs ControlNet face models in Forge (not only modules).  
- Comfy strong lock not wired yet.  
- Map avatar still prefers face when present.

See also: [ConnectImages.md](ConnectImages.md).
