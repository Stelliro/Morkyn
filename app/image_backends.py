"""
Optional local image backends: Forge / A1111 WebUI and ComfyUI.

Kept separate from the LLM stack. Default is off — nothing phones home.
Users point Mørkyn at a local URL when they want portraits / map art later.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from app.db import connect

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = Path(__file__).resolve().parent / "comfy_workflows"
PORTRAIT_DIR = ROOT / "data" / "portraits"
PRESETS_DEFAULT_PATH = ROOT / "config" / "image_presets.default.json"
PRESETS_USER_PATH = ROOT / "data" / "image_presets.json"

# Defaults match common local installs.
DEFAULT_FORGE_URL = "http://127.0.0.1:7860"
DEFAULT_COMFY_URL = "http://127.0.0.1:8188"

IMAGE_CONFIG_KEY = "image_config"
PLAYER_PORTRAIT_KEY = "player_portrait"
PLAYER_FULLBODY_KEY = "player_fullbody"

# Track last launched backend PID (best-effort, process-local).
_last_launch: dict[str, Any] = {}
_last_launch_mono: float = 0.0
# Long cooldown: first Forge boot often takes several minutes; never open a second window.
_LAUNCH_COOLDOWN_S = 300.0


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def default_image_config() -> dict[str, Any]:
    return {
        # off | forge | comfyui | demo (built-in test generator, no external app)
        "provider": _env("AI_RPG_IMAGE_PROVIDER", "off"),
        "forge_base_url": _env("AI_RPG_FORGE_URL", DEFAULT_FORGE_URL),
        "comfy_base_url": _env("AI_RPG_COMFY_URL", DEFAULT_COMFY_URL),
        "comfy_checkpoint": _env("AI_RPG_COMFY_CHECKPOINT", ""),
        "comfy_workflow": _env("AI_RPG_COMFY_WORKFLOW", "txt2img_api.json"),
        "default_width": _env_int("AI_RPG_IMAGE_WIDTH", 512),
        "default_height": _env_int("AI_RPG_IMAGE_HEIGHT", 512),
        "default_steps": _env_int("AI_RPG_IMAGE_STEPS", 20),
        "default_cfg": float(_env("AI_RPG_IMAGE_CFG", "7") or 7),
        # Keep negatives short. Child first at 1.3 (mild; avoid multi-tag age stacks).
        "negative_prompt": _env(
            "AI_RPG_IMAGE_NEGATIVE",
            "(child:1.3), lowres, blurry, deformed, bad anatomy, extra limbs, extra fingers, "
            "watermark, text, logo, multiple people, "
            "side profile, facing away, looking away, from behind, "
            "frame, border, picture frame",
        ),
        # Layer A: game-wide primary style prompts (studio-editable).
        "primary_prompt": _env("AI_RPG_IMAGE_PRIMARY_PROMPT", ""),
        "primary_negative": _env("AI_RPG_IMAGE_PRIMARY_NEGATIVE", ""),
        "portrait_style": _env(
            "AI_RPG_PORTRAIT_STYLE",
            "(portrait:1.5), facing camera, front view, looking at viewer, head and shoulders, single character",
        ),
        "timeout_seconds": _env_int("AI_RPG_IMAGE_TIMEOUT", 180),
        # Install roots (for Allow search / auto-launch). Also mirrored in presets.launch.
        "forge_root": _env("AI_RPG_FORGE_ROOT", ""),
        "comfy_root": _env("AI_RPG_COMFY_ROOT", ""),
        # When Generate requests launch_if_offline: hook first, then start once if needed.
        "auto_launch_if_offline": _env("AI_RPG_IMAGE_AUTO_LAUNCH", "1").lower()
        not in {"0", "false", "no", "off"},
        # Forge / A1111 generation defaults (grabbed from live catalog when available).
        "forge_checkpoint": _env("AI_RPG_FORGE_CHECKPOINT", ""),
        "forge_vae": _env("AI_RPG_FORGE_VAE", ""),
        "forge_sampler": _env("AI_RPG_FORGE_SAMPLER", "Euler a"),
        "forge_scheduler": _env("AI_RPG_FORGE_SCHEDULER", "Automatic"),
        "forge_clip_skip": _env_int("AI_RPG_FORGE_CLIP_SKIP", 1),
        "forge_restore_faces": False,
        "forge_tiling": False,
        "forge_enable_hr": False,
        "forge_hr_scale": 1.5,
        "forge_hr_upscaler": "Latent",
        "forge_denoising_strength": 0.45,
        # Light cross-image ref (img2img denoise). Strong uses ControlNet InstantID/IP-Adapter when installed.
        "fullbody_use_face_ref": True,
        # Higher denoise = weaker composition lock (freer full-body pose). Face is
        # composited into a tall canvas so 0.80–0.90 keeps likeness without portrait crop.
        "fullbody_ref_denoise": 0.88,
        # off | light | strong | auto
        # Default light: reliable img2img face ref. Strong/Auto only if API-safe ControlNet face models exist.
        "character_consistency": "light",
        "character_lock_weight": 0.65,
        # ADetailer (optional face/hand/person re-detail after gen — needs extension in Forge).
        "adetailer_enable": False,
        "adetailer_model": "face_yolov8n.pt",
        "adetailer_denoise": 0.4,
        "adetailer_on_face": True,
        "adetailer_on_fullbody": True,
        # When a face image exists, preserve it through ADetailer (identity-aware settings + light lock).
        # Stock ADetailer has no external ref-image field — we lock face into the gen, then AD refines.
        "adetailer_use_face_ref": True,
        # Main game: auto-generate portraits for newly seen NPCs (never the player).
        "auto_generate_npc_portraits": False,
        # Infinite Image Browsing (MIT extension) — optional port into Mørkyn UI.
        # open modes: embed (iframe in Mørkyn) | tab (new browser tab) | off
        "iib_open_mode": _env("AI_RPG_IIB_OPEN_MODE", "embed"),
        # Empty = derive from forge_base_url + /infinite_image_browsing/
        "iib_base_url": _env("AI_RPG_IIB_URL", ""),
        # Comfy extras beyond checkpoint/workflow
        "comfy_sampler_name": _env("AI_RPG_COMFY_SAMPLER", "euler"),
        "comfy_scheduler": _env("AI_RPG_COMFY_SCHEDULER", "normal"),
    }


def _normalize_provider(raw: Any) -> str:
    value = str(raw or "off").strip().lower()
    aliases = {
        "off": "off",
        "none": "off",
        "disabled": "off",
        "forge": "forge",
        "forgesd": "forge",
        "a1111": "forge",
        "automatic1111": "forge",
        "sdwebui": "forge",
        "webui": "forge",
        "comfy": "comfyui",
        "comfyui": "comfyui",
        "demo": "demo",
        "test": "demo",
        "builtin": "demo",
        "mock": "demo",
    }
    return aliases.get(value, "off")


def get_image_config() -> dict[str, Any]:
    base = default_image_config()
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (IMAGE_CONFIG_KEY,),
            ).fetchone()
    except Exception:
        base["provider"] = _normalize_provider(base["provider"])
        return base
    if not row:
        base["provider"] = _normalize_provider(base["provider"])
        return base
    try:
        stored = json.loads(row["value"])
    except json.JSONDecodeError:
        base["provider"] = _normalize_provider(base["provider"])
        return base
    if not isinstance(stored, dict):
        base["provider"] = _normalize_provider(base["provider"])
        return base
    merged = {**base, **stored}
    # Env overrides win when set (same spirit as LLM config).
    env_map = {
        "provider": "AI_RPG_IMAGE_PROVIDER",
        "forge_base_url": "AI_RPG_FORGE_URL",
        "comfy_base_url": "AI_RPG_COMFY_URL",
        "comfy_checkpoint": "AI_RPG_COMFY_CHECKPOINT",
        "comfy_workflow": "AI_RPG_COMFY_WORKFLOW",
        "negative_prompt": "AI_RPG_IMAGE_NEGATIVE",
        "portrait_style": "AI_RPG_PORTRAIT_STYLE",
        "forge_checkpoint": "AI_RPG_FORGE_CHECKPOINT",
        "forge_vae": "AI_RPG_FORGE_VAE",
        "forge_sampler": "AI_RPG_FORGE_SAMPLER",
        "forge_scheduler": "AI_RPG_FORGE_SCHEDULER",
        "comfy_sampler_name": "AI_RPG_COMFY_SAMPLER",
        "comfy_scheduler": "AI_RPG_COMFY_SCHEDULER",
    }
    for key, env_name in env_map.items():
        value = os.getenv(env_name)
        if value is not None and str(value).strip():
            merged[key] = str(value).strip()
    merged["provider"] = _normalize_provider(merged.get("provider"))
    for int_key, env_name, default in (
        ("default_width", "AI_RPG_IMAGE_WIDTH", 512),
        ("default_height", "AI_RPG_IMAGE_HEIGHT", 512),
        ("default_steps", "AI_RPG_IMAGE_STEPS", 20),
        ("timeout_seconds", "AI_RPG_IMAGE_TIMEOUT", 180),
    ):
        if os.getenv(env_name):
            merged[int_key] = _env_int(env_name, default)
        else:
            try:
                merged[int_key] = int(merged.get(int_key, default))
            except (TypeError, ValueError):
                merged[int_key] = default
    try:
        merged["default_cfg"] = float(merged.get("default_cfg", 7))
    except (TypeError, ValueError):
        merged["default_cfg"] = 7.0
    return merged


def update_image_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = get_image_config()
    allowed = {
        "provider",
        "forge_base_url",
        "comfy_base_url",
        "comfy_checkpoint",
        "comfy_workflow",
        "negative_prompt",
        "primary_prompt",
        "primary_negative",
        "portrait_style",
        "default_width",
        "default_height",
        "default_steps",
        "default_cfg",
        "timeout_seconds",
        "forge_root",
        "comfy_root",
        "auto_launch_if_offline",
        "forge_checkpoint",
        "forge_vae",
        "forge_sampler",
        "forge_scheduler",
        "forge_clip_skip",
        "forge_restore_faces",
        "forge_tiling",
        "forge_enable_hr",
        "forge_hr_scale",
        "forge_hr_upscaler",
        "forge_denoising_strength",
        "fullbody_use_face_ref",
        "fullbody_ref_denoise",
        "character_consistency",
        "character_lock_weight",
        "adetailer_enable",
        "adetailer_model",
        "adetailer_denoise",
        "adetailer_on_face",
        "adetailer_on_fullbody",
        "adetailer_use_face_ref",
        "auto_generate_npc_portraits",
        "iib_open_mode",
        "iib_base_url",
        "comfy_sampler_name",
        "comfy_scheduler",
    }
    bool_keys = {
        "auto_launch_if_offline",
        "forge_restore_faces",
        "forge_tiling",
        "forge_enable_hr",
        "fullbody_use_face_ref",
        "adetailer_enable",
        "adetailer_on_face",
        "adetailer_on_fullbody",
        "adetailer_use_face_ref",
        "auto_generate_npc_portraits",
    }
    int_keys = {
        "default_width",
        "default_height",
        "default_steps",
        "timeout_seconds",
        "forge_clip_skip",
    }
    float_keys = {
        "default_cfg",
        "forge_hr_scale",
        "forge_denoising_strength",
        "fullbody_ref_denoise",
        "character_lock_weight",
        "adetailer_denoise",
    }
    next_cfg = {**current}
    for key in allowed:
        if key not in payload:
            continue
        if key in int_keys:
            try:
                next_cfg[key] = int(payload.get(key))
            except (TypeError, ValueError):
                continue
        elif key in float_keys:
            try:
                next_cfg[key] = float(payload.get(key))
            except (TypeError, ValueError):
                continue
        elif key in bool_keys:
            next_cfg[key] = bool(payload.get(key))
        else:
            next_cfg[key] = str(payload.get(key) or "").strip()
    next_cfg["provider"] = _normalize_provider(next_cfg.get("provider"))
    # Normalize paths (Windows paste often leaves trailing spaces/quotes).
    for path_key in ("forge_root", "comfy_root", "forge_checkpoint", "comfy_checkpoint", "forge_vae"):
        if path_key in next_cfg and next_cfg[path_key] is not None:
            next_cfg[path_key] = str(next_cfg[path_key]).strip().strip('"').strip("'")
    next_cfg["default_width"] = max(64, min(2048, int(next_cfg.get("default_width") or 512)))
    next_cfg["default_height"] = max(64, min(2048, int(next_cfg.get("default_height") or 512)))
    next_cfg["default_steps"] = max(1, min(150, int(next_cfg.get("default_steps") or 20)))
    next_cfg["timeout_seconds"] = max(10, min(900, int(next_cfg.get("timeout_seconds") or 180)))
    next_cfg["forge_clip_skip"] = max(1, min(12, int(next_cfg.get("forge_clip_skip") or 1)))
    next_cfg["forge_hr_scale"] = max(1.0, min(4.0, float(next_cfg.get("forge_hr_scale") or 1.5)))
    next_cfg["forge_denoising_strength"] = max(0.0, min(1.0, float(next_cfg.get("forge_denoising_strength") or 0.45)))
    next_cfg["fullbody_ref_denoise"] = max(0.55, min(0.95, float(next_cfg.get("fullbody_ref_denoise") or 0.88)))
    next_cfg["character_lock_weight"] = max(0.1, min(1.5, float(next_cfg.get("character_lock_weight") or 0.65)))
    next_cfg["adetailer_denoise"] = max(0.1, min(0.9, float(next_cfg.get("adetailer_denoise") or 0.4)))
    ad_model = str(next_cfg.get("adetailer_model") or "face_yolov8n.pt").strip() or "face_yolov8n.pt"
    next_cfg["adetailer_model"] = ad_model[:120]
    cons = str(next_cfg.get("character_consistency") or "light").strip().lower()
    if cons not in {"off", "light", "strong", "auto"}:
        cons = "light"
    next_cfg["character_consistency"] = cons
    for bk in bool_keys:
        next_cfg[bk] = bool(next_cfg.get(bk))
    # Keep presets.launch roots in sync when set via image config.
    try:
        presets = load_image_presets()
        launch = presets.setdefault("launch", {})
        if isinstance(launch, dict):
            if next_cfg.get("forge_root") is not None:
                launch["forge_root"] = str(next_cfg.get("forge_root") or "")
            if next_cfg.get("comfy_root") is not None:
                launch["comfy_root"] = str(next_cfg.get("comfy_root") or "")
            launch["auto_launch_if_offline"] = bool(next_cfg.get("auto_launch_if_offline"))
            save_image_presets(presets)
    except Exception:
        pass
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (IMAGE_CONFIG_KEY, json.dumps(next_cfg, ensure_ascii=True)),
        )
    return public_image_config(next_cfg)


def public_image_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or get_image_config())
    cfg["provider"] = _normalize_provider(cfg.get("provider"))
    cfg["providers"] = {
        "off": {"label": "Off (no image backend)", "default_url": ""},
        "demo": {
            "label": "Demo (built-in test images)",
            "default_url": "",
            "docs": "No Forge/Comfy required. Generates solid-color labeled PNGs for UI testing.",
        },
        "forge": {
            "label": "Forge / A1111 (sdapi)",
            "default_url": DEFAULT_FORGE_URL,
            "docs": "Uses POST /sdapi/v1/txt2img — works with SD WebUI Forge and Automatic1111.",
        },
        "comfyui": {
            "label": "ComfyUI",
            "default_url": DEFAULT_COMFY_URL,
            "docs": "Uses /prompt + /history. Optional workflow JSON under app/comfy_workflows/.",
        },
    }
    cfg["enabled"] = cfg["provider"] in {"forge", "comfyui", "demo"}
    return cfg


def _http_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc


def _http_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"HTTP {exc.code} fetching image: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot fetch image: {exc.reason}") from exc


def list_comfy_workflows() -> list[str]:
    """API-format workflow JSON files under app/comfy_workflows/."""
    if not WORKFLOW_DIR.is_dir():
        return ["txt2img_api.json"]
    names = sorted(
        p.name
        for p in WORKFLOW_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".json"
    )
    return names or ["txt2img_api.json"]


def _checkpoint_dirs_for_root(root: Path) -> list[Path]:
    """Candidate folders that hold .safetensors / .ckpt checkpoints."""
    candidates = [
        root / "models" / "Stable-diffusion",
        root / "models" / "checkpoints",
        root / "models" / "Stable-diffusion" / "SDXL",
        root.parent / "models" / "Stable-diffusion",
        root.parent / "models" / "checkpoints",
        root / "webui" / "models" / "Stable-diffusion",
    ]
    # Deduplicate existing dirs
    seen: set[str] = set()
    out: list[Path] = []
    for path in candidates:
        try:
            key = str(path.resolve()).lower() if path.exists() else str(path).lower()
        except Exception:
            key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_dir():
            out.append(path)
    return out


def _forge_install_roots(forge_root: str | None = None) -> list[Path]:
    """Configured Forge/WebUI roots only (no machine-specific hardcodes)."""
    cfg = get_image_config()
    roots: list[Path] = []
    for raw in (forge_root, cfg.get("forge_root")):
        text = str(raw or "").strip().strip('"').strip("'")
        if not text:
            continue
        p = Path(text)
        if p not in roots:
            roots.append(p)
    return roots


def _scan_model_files(
    roots: list[Path],
    *,
    folder_names: tuple[str, ...],
    exts: set[str],
    max_depth: int = 2,
) -> list[str]:
    """Collect unique filenames under models/<folder> (and a few common alt paths)."""
    names: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        candidates: list[Path] = []
        for fname in folder_names:
            candidates.append(root / "models" / fname)
            candidates.append(root / "webui" / "models" / fname)
            candidates.append(root / fname)
            candidates.append(root / "models" / "Stable-diffusion" / fname)
        for folder in candidates:
            if not folder.is_dir():
                continue
            try:
                for path in folder.rglob("*"):
                    if not path.is_file():
                        continue
                    try:
                        rel = path.relative_to(folder)
                        if len(rel.parts) > max_depth:
                            continue
                    except ValueError:
                        continue
                    if path.suffix.lower() not in exts:
                        continue
                    name = path.name
                    if name.lower().startswith("put "):
                        continue
                    key = name.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    names.append(name)
            except OSError:
                continue
    names.sort(key=lambda n: n.lower())
    return names


def _list_local_vaes(forge_root: str | None = None) -> list[str]:
    """
    List VAE names from disk. Forge often 404s GET /sdapi/v1/sd-vae,
    so catalog always merges this with any live API list.
    """
    names: list[str] = ["Automatic", "None"]
    seen = {n.lower() for n in names}
    disk = _scan_model_files(
        _forge_install_roots(forge_root),
        folder_names=("VAE", "vae", "VAEs", "vae_approx", "VAE-approx"),
        exts={".safetensors", ".pt", ".ckpt", ".pth"},
        max_depth=2,
    )
    for name in disk:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _list_local_upscalers(forge_root: str | None = None) -> list[str]:
    """
    Latent modes + ESRGAN/RealESRGAN/SwinIR/etc. files under the Forge install.
    Merged with GET /sdapi/v1/upscalers when the API is up.
    """
    names: list[str] = [
        "Latent",
        "Latent (antialiased)",
        "Latent (bicubic)",
        "Latent (bicubic antialiased)",
        "Latent (nearest)",
        "Latent (nearest-exact)",
        "Nearest",
        "Nearest-exact",
        "Bilinear",
        "Bicubic",
    ]
    seen = {n.lower() for n in names}
    disk = _scan_model_files(
        _forge_install_roots(forge_root),
        folder_names=(
            "ESRGAN",
            "RealESRGAN",
            "SwinIR",
            "SwinIR_4x",
            "DAT",
            "HAT",
            "ScuNET",
            "BSRGAN",
            "LDSR",
            "Upscale",
            "upscale_models",
            "upscalers",
        ),
        exts={".safetensors", ".pt", ".pth", ".onnx", ".bin"},
        max_depth=3,
    )
    for name in disk:
        # Forge API often uses stem or full name — keep filename for selectability
        stem = Path(name).stem
        for candidate in (name, stem):
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(candidate)
    return names


def _merge_unique_names(*lists: list[str], head: list[str] | None = None) -> list[str]:
    """Stable merge: keep order, drop empties/dupes (case-insensitive)."""
    out: list[str] = []
    seen: set[str] = set()
    for name in list(head or []) + [n for lst in lists for n in (lst or [])]:
        text = str(name or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _catalog_item_name(item: Any) -> str:
    """Extract a display/API name from sampler/VAE/upscaler list entries."""
    if isinstance(item, dict):
        for key in (
            "name",
            "label",
            "model_name",
            "filename",
            "title",
            "model_path",
            "path",
        ):
            val = item.get(key)
            if val is not None and str(val).strip():
                text = str(val).strip().replace("\\", "/")
                # Prefer basename for path-like entries (VAEs often ship full paths)
                if "/" in text and key in {"filename", "model_path", "path", "model_name"}:
                    text = text.rsplit("/", 1)[-1]
                return text
        return ""
    return str(item or "").strip()


# Common A1111/Forge sampler names used when the API is offline (supplements live list).
_SAMPLER_FALLBACK: list[str] = [
    "Euler a",
    "Euler",
    "LMS",
    "Heun",
    "DPM2",
    "DPM2 a",
    "DPM++ 2S a",
    "DPM++ 2M",
    "DPM++ 2M Karras",
    "DPM++ SDE",
    "DPM++ SDE Karras",
    "DPM++ 2M SDE",
    "DPM++ 2M SDE Heun",
    "DPM++ 2M SDE Exponential",
    "DPM++ 3M SDE",
    "DPM++ 3M SDE Karras",
    "DPM++ 3M SDE Exponential",
    "DPM fast",
    "DPM adaptive",
    "LMS Karras",
    "DPM2 Karras",
    "DPM2 a Karras",
    "DPM++ 2S a Karras",
    "Restart",
    "DDIM",
    "PLMS",
    "UniPC",
    "LCM",
    "DDPM",
    "HeunPP2",
    "IPNDM",
    "IPNDM_V",
    "DEIS",
]

_SCHEDULER_FALLBACK: list[str] = [
    "Automatic",
    "Uniform",
    "Karras",
    "Exponential",
    "Polyexponential",
    "SGM Uniform",
    "KL Optimal",
    "Align Your Steps",
    "Simple",
    "Normal",
    "DDIM",
    "Beta",
    "Turbo",
    "Align Your Steps GITS",
    "Align Your Steps 11",
    "Align Your Steps 32",
]


def _seed_forge_catalog_lists(out: dict[str, Any], cfg: dict[str, Any]) -> None:
    """
    Always populate samplers/schedulers/VAEs/upscalers from disk + sensible fallbacks.
    Live API results are merged on top later (API names first).
    """
    forge = out.setdefault("forge", {})
    forge["samplers"] = _merge_unique_names(
        forge.get("samplers") or [],
        list(_SAMPLER_FALLBACK),
    )
    forge["schedulers"] = _merge_unique_names(
        forge.get("schedulers") or [],
        list(_SCHEDULER_FALLBACK),
    )
    disk_vaes = _list_local_vaes(cfg.get("forge_root"))
    forge["vaes"] = _merge_unique_names(
        forge.get("vaes") or [],
        disk_vaes,
        head=["Automatic", "None"],
    )
    disk_ups = _list_local_upscalers(cfg.get("forge_root"))
    forge["upscalers"] = _merge_unique_names(
        forge.get("upscalers") or [],
        disk_ups,
    )
    # Keep the user's currently saved choices visible even if not on disk/API yet
    for field, key in (
        ("samplers", "forge_sampler"),
        ("schedulers", "forge_scheduler"),
        ("vaes", "forge_vae"),
        ("upscalers", "forge_hr_upscaler"),
    ):
        cur = str(cfg.get(key) or "").strip()
        if cur:
            forge[field] = _merge_unique_names(forge.get(field) or [], [cur])


def _normalize_checkpoint_key(name: str) -> str:
    """
    Collapse API titles and disk filenames to one key for de-duplication.
    Forge API often returns 'foo.safetensors [abc123…]' while disk is 'foo.safetensors'.
    """
    text = str(name or "").strip().replace("\\", "/")
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    # Strip trailing hash suffix: " name [deadbeef]" or " name [deadbeefdeadbeef]"
    text = re.sub(r"\s*\[[0-9a-fA-F]{6,64}\]\s*$", "", text).strip()
    # Drop extension for matching (API may omit or vary casing)
    lower = text.lower()
    for ext in (".safetensors", ".ckpt", ".pt", ".pth"):
        if lower.endswith(ext):
            text = text[: -len(ext)]
            break
    return text.lower().strip()


def _dedupe_checkpoint_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer API entries; keep one row per normalized checkpoint identity."""
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in models:
        if not isinstance(raw, dict):
            title = str(raw or "").strip()
            if not title:
                continue
            item: dict[str, Any] = {"title": title, "model_name": title, "source": "unknown"}
        else:
            item = dict(raw)
            title = str(item.get("title") or item.get("model_name") or "").strip()
            if not title:
                continue
            item["title"] = title
            item.setdefault("model_name", title)
        key = _normalize_checkpoint_key(title) or title.lower()
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = item
            order.append(key)
            continue
        # Keep one row: prefer API metadata, but prefer a clean filename (no [hash]) for title
        prev_title = str(prev.get("title") or "")
        new_title = str(item.get("title") or "")
        prev_has_hash = bool(re.search(r"\[[0-9a-fA-F]{6,64}\]\s*$", prev_title))
        new_has_hash = bool(re.search(r"\[[0-9a-fA-F]{6,64}\]\s*$", new_title))
        merged = dict(prev)
        prev_src = str(prev.get("source") or "")
        new_src = str(item.get("source") or "")
        if prev_src != "api" and new_src == "api":
            merged = dict(item)
            # Keep cleaner display title if the previous disk name had no hash
            if prev_has_hash is False and new_has_hash and prev_title:
                merged["title"] = prev_title
                merged["model_name"] = prev.get("model_name") or prev_title
        elif new_src == prev_src:
            # Same source: prefer non-hash / shorter basename
            if prev_has_hash and not new_has_hash:
                merged = dict(item)
            elif not prev_has_hash and new_has_hash:
                pass
            elif len(new_title) < len(prev_title):
                merged = dict(item)
        else:
            # disk arriving after api — keep api flags but clean title if disk is cleaner
            if prev_has_hash and not new_has_hash and new_title:
                merged["title"] = new_title
                merged["model_name"] = item.get("model_name") or new_title
            if item.get("path") and not merged.get("path"):
                merged["path"] = item["path"]
        by_key[key] = merged
    return [by_key[k] for k in order]


def list_local_checkpoints(forge_root: str | None = None, comfy_root: str | None = None) -> list[dict[str, str]]:
    """Scan disk for checkpoint files so the UI can pick without API being up."""
    cfg = get_image_config()
    roots: list[Path] = []
    seen_roots: set[str] = set()
    for raw in (
        forge_root if forge_root is not None else cfg.get("forge_root"),
        comfy_root if comfy_root is not None else cfg.get("comfy_root"),
    ):
        text = str(raw or "").strip().strip('"').strip("'")
        if not text:
            continue
        try:
            key = str(Path(text).resolve()).lower()
        except Exception:
            key = text.lower()
        if key in seen_roots:
            continue
        seen_roots.add(key)
        roots.append(Path(text))
    # Only configured install roots — never hardcode a machine-specific path.

    found: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    seen_paths: set[str] = set()
    exts = {".safetensors", ".ckpt", ".pt", ".pth"}
    for root in roots:
        for folder in _checkpoint_dirs_for_root(root):
            try:
                for path in folder.rglob("*"):
                    if not path.is_file():
                        continue
                    if path.suffix.lower() not in exts:
                        continue
                    if path.name.lower().startswith("put "):
                        continue
                    try:
                        path_key = str(path.resolve()).lower()
                    except Exception:
                        path_key = str(path).lower()
                    if path_key in seen_paths:
                        continue
                    name = path.name
                    name_key = _normalize_checkpoint_key(name) or name.lower()
                    if name_key in seen_keys:
                        continue
                    seen_paths.add(path_key)
                    seen_keys.add(name_key)
                    found.append(
                        {
                            "title": name,
                            "model_name": name,
                            "path": str(path),
                            "source": "disk",
                        }
                    )
            except Exception:
                continue
    found.sort(key=lambda m: m.get("title") or "")
    return found


def fetch_backend_catalog(provider: str | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Pull live options from Forge/Comfy when the API is up.
    Always seeds disk checkpoints/VAEs/upscalers + sampler fallbacks so the UI
    can list the user's assets even when the backend is offline.
    """
    cfg = get_image_config() if config is None else dict(config)
    provider = _normalize_provider(provider or cfg.get("provider"))
    disk_models = _dedupe_checkpoint_models(
        list_local_checkpoints(cfg.get("forge_root"), cfg.get("comfy_root"))
    )
    out: dict[str, Any] = {
        "provider": provider,
        "ok": False,
        "message": "",
        "forge": {
            "models": list(disk_models),  # seed with on-disk checkpoints immediately
            "samplers": [],
            "schedulers": [],
            "vaes": [],
            "upscalers": [],
            "loras": [],
            "options": {},
            "disk_models": disk_models,
        },
        "comfyui": {
            "checkpoints": [m["title"] for m in disk_models],
            "samplers": [],
            "schedulers": [],
            "vaes": [],
            "upscalers": [],
            "workflows": list_comfy_workflows(),
            "disk_models": disk_models,
        },
        "disk_checkpoints": disk_models,
    }
    # Offline-safe seed: disk VAEs/upscalers + full sampler/scheduler fallback lists
    _seed_forge_catalog_lists(out, cfg)

    if provider == "off":
        out["message"] = (
            f"Provider is off — {len(disk_models)} checkpoint(s), "
            f"{len(out['forge']['vaes'])} VAE(s), "
            f"{len(out['forge']['upscalers'])} upscaler(s) on disk / fallbacks. "
            "Pick Forge/Comfy/Demo to generate; Refresh catalog when the API is up for live lists."
        )
        out["ok"] = True
        return out
    if provider == "demo":
        out["ok"] = True
        out["message"] = (
            f"Demo mode — {len(disk_models)} local checkpoint file(s) listed (not used by demo). "
            f"{len(out['forge']['samplers'])} sampler fallback(s) ready if you switch to Forge."
        )
        return out
    try:
        if provider == "forge":
            found = discover_backend_base_url("forge", cfg, persist=True)
            base = str(
                (found.get("base_url") if found.get("ok") else None)
                or cfg.get("forge_base_url")
                or DEFAULT_FORGE_URL
            ).rstrip("/")
            api_online = bool(found.get("ok"))
            # Offline: keep disk/fallback seeds — do not hammer every API route with timeouts
            if not api_online:
                out["forge"]["models"] = _dedupe_checkpoint_models(list(disk_models))
                out["ok"] = True
                out["message"] = (
                    f"Forge API offline at {base} — using disk/fallback catalog: "
                    f"{len(out['forge']['models'])} model(s), "
                    f"{len(out['forge']['samplers'])} sampler(s), "
                    f"{len(out['forge']['vaes'])} VAE(s), "
                    f"{len(out['forge']['upscalers'])} upscaler(s). "
                    "Start Forge and Refresh catalog for the live full list."
                )
                return out
            # Models (API titles often include hash suffix — prefer API when online)
            try:
                models = _http_json("GET", f"{base}/sdapi/v1/sd-models", timeout=12)
                if isinstance(models, list) and models:
                    api_online = True
                    api_models = [
                        {
                            "title": str(m.get("title") or m.get("model_name") or ""),
                            "model_name": str(m.get("model_name") or m.get("title") or ""),
                            "hash": str(m.get("hash") or ""),
                            "source": "api",
                        }
                        for m in models
                        if isinstance(m, dict)
                    ]
                    # Merge API + disk, de-dupe by basename (API hash suffixes collapse)
                    out["forge"]["models"] = _dedupe_checkpoint_models([*api_models, *disk_models])
                else:
                    out["forge"]["models"] = _dedupe_checkpoint_models(list(disk_models))
            except Exception as exc:
                out["message"] = f"API models unavailable ({exc}); using {len(disk_models)} disk checkpoint(s)."
                out["forge"]["models"] = _dedupe_checkpoint_models(list(disk_models))
            try:
                loras = _http_json("GET", f"{base}/sdapi/v1/loras", timeout=12)
                if isinstance(loras, list):
                    out["forge"]["loras"] = [
                        {
                            "name": str(
                                (m.get("name") if isinstance(m, dict) else None)
                                or (m.get("alias") if isinstance(m, dict) else None)
                                or m
                                or ""
                            ),
                            "alias": str((m.get("alias") if isinstance(m, dict) else "") or ""),
                        }
                        for m in loras
                        if (isinstance(m, dict) and (m.get("name") or m.get("alias")))
                        or (not isinstance(m, dict) and str(m).strip())
                    ][:800]
            except Exception:
                out["forge"]["loras"] = []

            # --- Samplers: live API first (all user/extension samplers), then fallbacks ---
            api_samplers: list[str] = []
            for route in ("/sdapi/v1/samplers", "/sdapi/v1/samplers-list"):
                try:
                    samplers = _http_json("GET", f"{base}{route}", timeout=12)
                    if isinstance(samplers, list) and samplers:
                        api_samplers = [
                            n for n in (_catalog_item_name(s) for s in samplers) if n
                        ]
                        if api_samplers:
                            api_online = True
                            break
                except Exception:
                    continue
            out["forge"]["samplers"] = _merge_unique_names(
                api_samplers,
                out["forge"].get("samplers") or [],
                list(_SAMPLER_FALLBACK),
            )

            # --- Schedulers ---
            api_schedulers: list[str] = []
            for route in ("/sdapi/v1/schedulers", "/sdapi/v1/scheduler-list"):
                try:
                    schedulers = _http_json("GET", f"{base}{route}", timeout=10)
                    if isinstance(schedulers, list) and schedulers:
                        api_schedulers = [
                            n for n in (_catalog_item_name(s) for s in schedulers) if n
                        ]
                        if api_schedulers:
                            break
                except Exception:
                    continue
            out["forge"]["schedulers"] = _merge_unique_names(
                api_schedulers,
                out["forge"].get("schedulers") or [],
                list(_SCHEDULER_FALLBACK),
            )

            # --- VAEs: live API + disk + currently loaded option ---
            api_vaes: list[str] = []
            for route in ("/sdapi/v1/sd-vae", "/sdapi/v1/sd-vaes", "/sdapi/v1/modules"):
                try:
                    vaes = _http_json("GET", f"{base}{route}", timeout=8)
                    if isinstance(vaes, list) and vaes:
                        for v in vaes:
                            name = _catalog_item_name(v)
                            if name:
                                api_vaes.append(name)
                        if api_vaes:
                            break
                    if isinstance(vaes, dict):
                        for key in ("VAE", "vae", "sd_vae", "vaes"):
                            block = vaes.get(key)
                            if isinstance(block, list):
                                for v in block:
                                    name = _catalog_item_name(v)
                                    if name:
                                        api_vaes.append(name)
                except Exception:
                    continue
            out["forge"]["vaes"] = _merge_unique_names(
                api_vaes,
                out["forge"].get("vaes") or [],
                head=["Automatic", "None"],
            )

            # --- Hires / general upscalers: all API routes + Latent modes + disk ---
            api_ups: list[str] = []
            for route in (
                "/sdapi/v1/upscalers",
                "/sdapi/v1/latent-upscale-modes",
                "/sdapi/v1/realesrgan-models",
            ):
                try:
                    ups = _http_json("GET", f"{base}{route}", timeout=12)
                    if isinstance(ups, list) and ups:
                        for u in ups:
                            name = _catalog_item_name(u)
                            if name:
                                api_ups.append(name)
                except Exception:
                    continue
            out["forge"]["upscalers"] = _merge_unique_names(
                api_ups,
                out["forge"].get("upscalers") or [],
            )

            try:
                options = _http_json("GET", f"{base}/sdapi/v1/options", timeout=10)
                if isinstance(options, dict):
                    api_online = True
                    out["forge"]["options"] = {
                        "sd_model_checkpoint": options.get("sd_model_checkpoint"),
                        "sd_vae": options.get("sd_vae"),
                        "CLIP_stop_at_last_layers": options.get("CLIP_stop_at_last_layers"),
                        "samples_format": options.get("samples_format"),
                        "samples_save": options.get("samples_save"),
                        "samples_sampler": options.get("samples_sampler")
                        or options.get("sampler_name"),
                        "hr_upscaler": options.get("hr_upscaler"),
                    }
                    extras: list[tuple[str, Any]] = [
                        ("vaes", options.get("sd_vae")),
                        ("samplers", options.get("samples_sampler") or options.get("sampler_name")),
                        ("upscalers", options.get("hr_upscaler")),
                    ]
                    for field, raw in extras:
                        cur = str(raw or "").strip()
                        if not cur:
                            continue
                        if field == "vaes":
                            out["forge"][field] = _merge_unique_names(
                                out["forge"][field],
                                [cur],
                                head=["Automatic", "None"],
                            )
                        else:
                            out["forge"][field] = _merge_unique_names(
                                out["forge"][field],
                                [cur],
                            )
            except Exception:
                pass

            # Ensure user's currently selected config values always appear in dropdowns
            for field, key in (
                ("samplers", "forge_sampler"),
                ("schedulers", "forge_scheduler"),
                ("vaes", "forge_vae"),
                ("upscalers", "forge_hr_upscaler"),
            ):
                cur = str(cfg.get(key) or "").strip()
                if cur:
                    out["forge"][field] = _merge_unique_names(out["forge"][field], [cur])

            out["ok"] = True
            live_bit = "live API + " if api_online else "offline / "
            out["message"] = (
                out["message"]
                or (
                    f"Forge catalog ({live_bit}disk): {len(out['forge']['models'])} model(s), "
                    f"{len(out['forge']['samplers'])} sampler(s), "
                    f"{len(out['forge']['vaes'])} VAE(s), "
                    f"{len(out['forge']['upscalers'])} upscaler(s)."
                )
            )
            return out

        if provider == "comfyui":
            base = str(cfg.get("comfy_base_url") or DEFAULT_COMFY_URL).rstrip("/")
            # Prefer /models/checkpoints (newer), fall back to object_info
            checkpoints: list[str] = []
            try:
                ck = _http_json("GET", f"{base}/models/checkpoints", timeout=12)
                if isinstance(ck, list):
                    checkpoints = [str(x) for x in ck if x]
            except Exception:
                try:
                    info = _http_json("GET", f"{base}/object_info/CheckpointLoaderSimple", timeout=15)
                    node = info.get("CheckpointLoaderSimple") if isinstance(info, dict) else None
                    inputs = (node or {}).get("input", {}).get("required", {}) if isinstance(node, dict) else {}
                    ck_field = inputs.get("ckpt_name") if isinstance(inputs, dict) else None
                    if isinstance(ck_field, list) and ck_field and isinstance(ck_field[0], list):
                        checkpoints = [str(x) for x in ck_field[0]]
                except Exception as exc:
                    out["message"] = f"checkpoints: {exc}"
            # Merge live Comfy list with disk scan; de-dupe by basename
            merged_ck: list[dict[str, Any]] = [
                {"title": c, "model_name": c, "source": "api"} for c in checkpoints if c
            ]
            merged_ck.extend(disk_models)
            deduped_ck = _dedupe_checkpoint_models(merged_ck)
            out["comfyui"]["checkpoints"] = [m["title"] for m in deduped_ck]
            out["comfyui"]["disk_models"] = deduped_ck
            # Samplers / schedulers from KSampler object_info (full installed set)
            try:
                info = _http_json("GET", f"{base}/object_info/KSampler", timeout=15)
                node = info.get("KSampler") if isinstance(info, dict) else None
                required = (node or {}).get("input", {}).get("required", {}) if isinstance(node, dict) else {}
                samp = required.get("sampler_name") if isinstance(required, dict) else None
                sched = required.get("scheduler") if isinstance(required, dict) else None
                if isinstance(samp, list) and samp and isinstance(samp[0], list):
                    out["comfyui"]["samplers"] = [str(x) for x in samp[0]]
                if isinstance(sched, list) and sched and isinstance(sched[0], list):
                    out["comfyui"]["schedulers"] = [str(x) for x in sched[0]]
            except Exception:
                out["comfyui"]["samplers"] = [
                    "euler",
                    "euler_ancestral",
                    "heun",
                    "dpm_2",
                    "dpmpp_2m",
                    "dpmpp_sde",
                    "ddim",
                    "uni_pc",
                    "lcm",
                ]
                out["comfyui"]["schedulers"] = [
                    "normal",
                    "karras",
                    "exponential",
                    "sgm_uniform",
                    "simple",
                    "ddim_uniform",
                    "beta",
                ]
            # Comfy model folders for VAE + upscale models (when API lists them)
            for folder, key in (
                ("vae", "vaes"),
                ("upscale_models", "upscalers"),
            ):
                try:
                    items = _http_json("GET", f"{base}/models/{folder}", timeout=10)
                    if isinstance(items, list):
                        out["comfyui"][key] = [str(x) for x in items if x]
                except Exception:
                    out["comfyui"].setdefault(key, [])
            if not out["comfyui"].get("vaes"):
                out["comfyui"]["vaes"] = [
                    n
                    for n in _list_local_vaes(cfg.get("comfy_root"))
                    if n not in {"Automatic", "None"}
                ]
            if not out["comfyui"].get("upscalers"):
                out["comfyui"]["upscalers"] = _list_local_upscalers(cfg.get("comfy_root"))
            out["comfyui"]["workflows"] = list_comfy_workflows()
            out["ok"] = True
            out["message"] = out["message"] or (
                f"Comfy catalog: {len(out['comfyui']['checkpoints'])} checkpoint(s), "
                f"{len(out['comfyui']['samplers'])} sampler(s), "
                f"{len(out['comfyui'].get('vaes') or [])} VAE(s), "
                f"{len(out['comfyui'].get('upscalers') or [])} upscaler(s), "
                f"{len(out['comfyui']['workflows'])} local workflow(s)."
            )
            return out
    except Exception as exc:
        out["ok"] = False
        out["message"] = str(exc)
        # Keep disk/fallback seeds so the form still has something usable
        _seed_forge_catalog_lists(out, cfg)
        return out
    out["message"] = "Unknown provider"
    return out



# ---------------------------------------------------------------------------
# Infinite Image Browsing (IIB) — optional external extension port
# ---------------------------------------------------------------------------

IIB_GITHUB = "https://github.com/zanllp/sd-webui-infinite-image-browsing"
IIB_LICENSE = "MIT"
_IIB_FOLDER_NAMES = (
    "sd-webui-infinite-image-browsing",
    "infinite-image-browsing",
    "sd_webui_infinite_image_browsing",
)


def _iib_disk_install(forge_root: str | None = None) -> dict[str, Any]:
    """Locate IIB under a configured Forge root (extensions folder)."""
    cfg = get_image_config()
    root = str(forge_root if forge_root is not None else cfg.get("forge_root") or "").strip()
    out: dict[str, Any] = {
        "installed": False,
        "path": "",
        "forge_root": root,
        "message": "Forge root not set — cannot detect IIB on disk.",
    }
    if not root:
        return out
    layout = _forge_layout(root)
    candidates: list[Path] = []
    for folder in _IIB_FOLDER_NAMES:
        candidates.append(layout["webui"] / "extensions" / folder)
        candidates.append(layout["base"] / "extensions" / folder)
    for path in candidates:
        try:
            if path.is_dir() and any(path.iterdir()):
                out["installed"] = True
                out["path"] = str(path)
                out["message"] = "IIB extension folder found."
                return out
        except OSError:
            continue
    out["message"] = "IIB not found under extensions/ (install from Installs tab or Forge Extensions)."
    return out


def _iib_ui_urls(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    """Public URLs for opening / embedding IIB (user's Forge, not bundled)."""
    cfg = cfg or get_image_config()
    custom = str(cfg.get("iib_base_url") or "").strip().rstrip("/")
    forge = str(cfg.get("forge_base_url") or DEFAULT_FORGE_URL).rstrip("/")
    base = custom or f"{forge}/infinite_image_browsing"
    # Normalize trailing slash for embed
    ui = base if base.endswith("/") else base + "/"
    return {
        "base_url": base.rstrip("/"),
        "embed_url": ui,
        "open_url": ui,
        "forge_base_url": forge,
    }


def probe_iib_status(*, launch_if_offline: bool = False) -> dict[str, Any]:
    """
    Detect Infinite Image Browsing:
    - disk: extension folder under forge_root
    - online: HTTP GET to /infinite_image_browsing/ on Forge (or custom iib_base_url)
    Does not vendor or copy IIB code — only probes the user's install.
    """
    cfg = get_image_config()
    disk = _iib_disk_install(cfg.get("forge_root"))
    urls = _iib_ui_urls(cfg)
    mode = str(cfg.get("iib_open_mode") or "embed").strip().lower()
    if mode not in {"embed", "tab", "off"}:
        mode = "embed"

    online = False
    http_status = 0
    http_message = ""
    probe_url = urls["embed_url"]
    # Prefer a light path; some builds answer on either with/without slash
    candidates = [urls["embed_url"], urls["base_url"], f"{urls['forge_base_url']}/infinite_image_browsing"]
    seen: set[str] = set()
    for cand in candidates:
        key = cand.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        try:
            req = urllib.request.Request(
                cand if cand.endswith("/") else cand + "/",
                method="GET",
                headers={"User-Agent": "Morkyn/iib-probe"},
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                http_status = int(getattr(resp, "status", 200) or 200)
                # 200-399 and not pure 404
                if 200 <= http_status < 400:
                    online = True
                    probe_url = cand if cand.endswith("/") else cand + "/"
                    http_message = f"IIB responded HTTP {http_status}"
                    break
        except urllib.error.HTTPError as exc:
            http_status = int(exc.code or 0)
            # Some proxies return 401/403 when up but gated — still "there"
            if http_status in {401, 403}:
                online = True
                probe_url = cand if cand.endswith("/") else cand + "/"
                http_message = f"IIB reachable but auth required (HTTP {http_status})"
                break
            http_message = f"HTTP {http_status}"
        except Exception as exc:
            http_message = str(exc)[:200]

    if not online and launch_if_offline and cfg.get("auto_launch_if_offline"):
        # Only try launching Forge (not a separate IIB process).
        try:
            launch_image_backend("forge", force=False)
            # Re-probe once quickly
            time.sleep(1.5)
            return probe_iib_status(launch_if_offline=False)
        except Exception:
            pass

    usable = online and mode != "off"
    return {
        "ok": usable,
        "extension": "infinite-image-browsing",
        "license": IIB_LICENSE,
        "github": IIB_GITHUB,
        "open_mode": mode,
        "installed_on_disk": bool(disk.get("installed")),
        "disk_path": disk.get("path") or "",
        "disk_message": disk.get("message") or "",
        "online": online,
        "http_status": http_status,
        "http_message": http_message,
        "base_url": urls["base_url"],
        "embed_url": probe_url if online else urls["embed_url"],
        "open_url": probe_url if online else urls["open_url"],
        "message": (
            "IIB ready — open Image Browser in Mørkyn."
            if usable
            else (
                "IIB installed on disk but Forge API is offline — start Forge with --api, then reopen."
                if disk.get("installed") and not online
                else (
                    "IIB not detected. Install from LLM Settings → Images → Installs (or Forge Extensions), restart Forge."
                    if not disk.get("installed")
                    else http_message or "IIB unavailable"
                )
            )
        ),
        "can_embed": usable and mode == "embed",
        "can_open_tab": online and mode in {"embed", "tab"},
        "native_fallback": True,
        "note": (
            "Mørkyn does not ship IIB. When installed, the extension UI is shown via localhost "
            "iframe/tab (MIT). Native portrait grid is always available for data/portraits."
        ),
    }


def list_local_portraits(*, limit: int = 200) -> dict[str, Any]:
    """
    List images Mørkyn wrote under data/portraits (native browser fallback).
    Paths are relative; UI loads via /api/portraits/file?name=...
    """
    limit = max(1, min(500, int(limit or 200)))
    PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    try:
        files = [
            p
            for p in PORTRAIT_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        ]
    except OSError as exc:
        return {"ok": False, "error": str(exc), "items": [], "dir": str(PORTRAIT_DIR)}
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for path in files[:limit]:
        name = path.name
        low = name.lower()
        kind = "other"
        if "face" in low or "portrait" in low:
            kind = "face"
        elif "fullbody" in low or "full_body" in low or "body" in low:
            kind = "fullbody"
        elif "npc" in low:
            kind = "npc"
        try:
            st = path.stat()
            mtime = int(st.st_mtime)
            size = int(st.st_size)
        except OSError:
            mtime = 0
            size = 0
        items.append(
            {
                "id": name,
                "name": name,
                "kind": kind,
                "mtime": mtime,
                "size": size,
                "url": f"/api/portraits/file?name={urllib.parse.quote(name)}",
            }
        )
    return {
        "ok": True,
        "dir": "data/portraits",
        "count": len(items),
        "items": items,
    }


def resolve_portrait_file(name: str) -> Path | None:
    """Safe resolve of a file under data/portraits (no path traversal)."""
    raw = str(name or "").strip().replace("\\", "/")
    if not raw or "/" in raw or raw in {".", ".."} or ".." in raw:
        return None
    # Only bare filenames
    base = Path(raw).name
    if base != raw:
        return None
    PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    path = (PORTRAIT_DIR / base).resolve()
    try:
        if path.parent != PORTRAIT_DIR.resolve():
            return None
    except OSError:
        return None
    if path.is_file():
        return path
    return None


def delete_local_portrait(name: str) -> dict[str, Any]:
    """Delete one file under data/portraits (filename only)."""
    path = resolve_portrait_file(name)
    if not path:
        return {"ok": False, "error": "Portrait not found", "name": str(name or "")}
    try:
        path.unlink()
    except OSError as exc:
        return {"ok": False, "error": str(exc), "name": path.name}
    return {"ok": True, "deleted": path.name, "dir": "data/portraits"}


def _parse_base_host_port(base_url: str, default_port: int) -> tuple[str, int]:
    raw = str(base_url or "").strip() or f"http://127.0.0.1:{default_port}"
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urllib.parse.urlparse(raw)
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or default_port)
    return host, port


def _tcp_port_open(host: str, port: int, *, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _backend_listen_state(provider: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Whether something is already bound on the configured Forge/Comfy port."""
    provider = _normalize_provider(provider)
    if provider == "forge":
        base = str(cfg.get("forge_base_url") or DEFAULT_FORGE_URL).rstrip("/")
        host, port = _parse_base_host_port(base, 7860)
    elif provider == "comfyui":
        base = str(cfg.get("comfy_base_url") or DEFAULT_COMFY_URL).rstrip("/")
        host, port = _parse_base_host_port(base, 8188)
    else:
        return {"port_open": False, "base_url": "", "host": "", "port": 0}
    return {
        "port_open": _tcp_port_open(host, port),
        "base_url": base,
        "host": host,
        "port": port,
    }


def _forge_api_ok(base_url: str, *, timeout: int = 6) -> dict[str, Any]:
    """Return ok payload if base_url answers Forge/A1111 SD API."""
    base = str(base_url or "").rstrip("/")
    try:
        payload = _http_json("GET", f"{base}/sdapi/v1/sd-models", timeout=timeout)
        count = len(payload) if isinstance(payload, list) else 0
        return {
            "ok": True,
            "base_url": base,
            "models": count,
            "message": f"Forge/A1111 reachable — {count} checkpoint(s) listed.",
        }
    except Exception as first_exc:
        try:
            _http_json("GET", f"{base}/sdapi/v1/options", timeout=timeout)
            return {
                "ok": True,
                "base_url": base,
                "models": None,
                "message": "Forge/A1111 reachable (options).",
            }
        except Exception:
            return {"ok": False, "base_url": base, "message": str(first_exc)}


def _comfy_api_ok(base_url: str, *, timeout: int = 6) -> dict[str, Any]:
    base = str(base_url or "").rstrip("/")
    try:
        payload = _http_json("GET", f"{base}/system_stats", timeout=timeout)
        return {
            "ok": True,
            "base_url": base,
            "message": "ComfyUI reachable.",
            "system_stats": payload if isinstance(payload, dict) else {},
        }
    except Exception as exc:
        return {"ok": False, "base_url": base, "message": str(exc)}


def _candidate_ports(preferred: int, *, span: int = 8) -> list[int]:
    """Preferred first, then nearby ports (Forge often jumps 7860 → 7861 if busy)."""
    ports = [int(preferred)]
    for delta in range(1, span + 1):
        ports.append(int(preferred) + delta)
        if preferred - delta > 1024:
            ports.append(int(preferred) - delta)
    # de-dupe preserve order
    seen: set[int] = set()
    out: list[int] = []
    for p in ports:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def discover_backend_base_url(
    provider: str,
    config: dict[str, Any] | None = None,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """
    Find a live Forge/Comfy API URL.

    If the configured port is wrong (common: Forge bound 7861 while config says 7860),
    scan nearby open ports and optionally persist the working URL.
    """
    cfg = get_image_config() if config is None else dict(config)
    provider = _normalize_provider(provider or cfg.get("provider"))
    if provider == "forge":
        preferred = str(cfg.get("forge_base_url") or DEFAULT_FORGE_URL).rstrip("/")
        host, pref_port = _parse_base_host_port(preferred, 7860)
        scheme = "https" if preferred.lower().startswith("https") else "http"
        # 1) configured URL
        hit = _forge_api_ok(preferred, timeout=5)
        if hit.get("ok"):
            return {
                **hit,
                "provider": "forge",
                "discovered": False,
                "preferred": preferred,
            }
        # 2) nearby ports that are actually listening
        tried = [preferred]
        open_ports: list[int] = []
        for port in _candidate_ports(pref_port, span=10):
            if _tcp_port_open(host, port, timeout=0.35):
                open_ports.append(port)
        # Always try sequential candidates even if TCP check is flaky
        for port in _candidate_ports(pref_port, span=10):
            base = f"{scheme}://{host}:{port}"
            if base in tried:
                continue
            tried.append(base)
            # Skip slow HTTP if TCP clearly closed (except preferred which already failed)
            if port not in open_ports and not _tcp_port_open(host, port, timeout=0.25):
                continue
            hit = _forge_api_ok(base, timeout=4)
            if hit.get("ok"):
                if persist and base.rstrip("/") != preferred.rstrip("/"):
                    try:
                        update_image_config({"forge_base_url": base})
                    except Exception:
                        pass
                return {
                    **hit,
                    "provider": "forge",
                    "discovered": True,
                    "preferred": preferred,
                    "message": (
                        f"{hit.get('message')} "
                        f"(auto-found on port {port}; config had {pref_port})"
                    ),
                    "persisted": persist,
                }
        any_open = bool(open_ports)
        return {
            "ok": False,
            "provider": "forge",
            "base_url": preferred,
            "preferred": preferred,
            "port_open": any_open,
            "open_ports": open_ports,
            "tried": tried[:12],
            "message": (
                f"Cannot reach Forge API at {preferred}"
                + (f"; open ports nearby: {open_ports} but no /sdapi response" if open_ports else "")
                + f". Last error: {hit.get('message') if isinstance(hit, dict) else ''}"
            ),
        }

    if provider == "comfyui":
        preferred = str(cfg.get("comfy_base_url") or DEFAULT_COMFY_URL).rstrip("/")
        host, pref_port = _parse_base_host_port(preferred, 8188)
        scheme = "https" if preferred.lower().startswith("https") else "http"
        hit = _comfy_api_ok(preferred, timeout=5)
        if hit.get("ok"):
            return {**hit, "provider": "comfyui", "discovered": False, "preferred": preferred}
        open_ports = [p for p in _candidate_ports(pref_port, span=6) if _tcp_port_open(host, p, timeout=0.35)]
        for port in _candidate_ports(pref_port, span=6):
            base = f"{scheme}://{host}:{port}"
            if base.rstrip("/") == preferred.rstrip("/"):
                continue
            if port not in open_ports and not _tcp_port_open(host, port, timeout=0.25):
                continue
            hit = _comfy_api_ok(base, timeout=4)
            if hit.get("ok"):
                if persist and base.rstrip("/") != preferred.rstrip("/"):
                    try:
                        update_image_config({"comfy_base_url": base})
                    except Exception:
                        pass
                return {
                    **hit,
                    "provider": "comfyui",
                    "discovered": True,
                    "preferred": preferred,
                    "message": f"{hit.get('message')} (auto-found on port {port})",
                    "persisted": persist,
                }
        return {
            "ok": False,
            "provider": "comfyui",
            "base_url": preferred,
            "port_open": bool(open_ports),
            "open_ports": open_ports,
            "message": hit.get("message") if isinstance(hit, dict) else "ComfyUI not reachable",
        }

    return {"ok": False, "provider": provider, "message": "No discovery for this provider"}


def _windows_backend_process_running(provider: str, install_root: str = "") -> dict[str, Any]:
    """
    Best-effort: detect an already-running Forge/A1111 or ComfyUI python process
    so we never open a second terminal while the first is still booting.
    """
    if os.name != "nt":
        return {"running": False, "detail": ""}
    provider = _normalize_provider(provider)
    root_hint = str(install_root or "").strip().lower().replace("/", "\\")
    try:
        # Command lines of python processes (truncated).
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='python3.exe'\" "
                    "| Select-Object -ExpandProperty CommandLine"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=0x08000000,
        )
        lines = [ln.strip() for ln in (completed.stdout or "").splitlines() if ln.strip()]
    except Exception as exc:
        return {"running": False, "detail": f"process scan failed: {exc}"}

    hits: list[str] = []
    for line in lines:
        low = line.lower().replace("/", "\\")
        if provider == "forge":
            # Avoid bare "forge" (too many false positives). Require webui/launch markers.
            markers = (
                "launch_utils",
                "webui.py",
                "stable-diffusion-webui",
                "modules\\launch",
                "modules.launch",
                "forgesd",
                "webui-user.bat",
                "webui.bat",
            )
            if any(token in low for token in markers):
                hits.append(line[:180])
            elif root_hint and root_hint in low and ("webui" in low or "launch" in low):
                hits.append(line[:180])
        elif provider == "comfyui":
            if "comfyui" in low or ("main.py" in low and "comfy" in low):
                hits.append(line[:180])
            elif root_hint and root_hint in low and "main.py" in low:
                hits.append(line[:180])
    return {
        "running": bool(hits),
        "detail": hits[0] if hits else "",
        "count": len(hits),
    }


def probe_image_backend(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = get_image_config() if config is None else config
    provider = _normalize_provider(cfg.get("provider"))
    if provider == "off":
        return {
            "ok": True,
            "provider": "off",
            "message": "Image backend is off. Choose Demo, Forge, or ComfyUI in settings when you want local art.",
        }
    if provider == "demo":
        return {
            "ok": True,
            "provider": "demo",
            "message": "Demo generator ready (no external app). Face/full-body will be solid-color test PNGs.",
        }

    if provider in {"forge", "comfyui"}:
        # Discover live URL (handles Forge hopping 7860 → 7861 when default is busy).
        found = discover_backend_base_url(provider, cfg, persist=True)
        if found.get("ok"):
            return {
                "ok": True,
                "provider": provider,
                "base_url": found.get("base_url"),
                "port_open": True,
                "discovered": bool(found.get("discovered")),
                "message": found.get("message") or f"{provider} reachable.",
                "models": found.get("models"),
                "system_stats": found.get("system_stats"),
            }
        listen = _backend_listen_state(provider, cfg)
        # If we only know preferred port is open without API, keep loading message.
        port_open = bool(found.get("port_open") or listen.get("port_open"))
        open_ports = found.get("open_ports") or []
        if port_open or open_ports:
            return {
                "ok": False,
                "provider": provider,
                "base_url": found.get("base_url") or listen.get("base_url"),
                "port_open": True,
                "busy_or_loading": True,
                "open_ports": open_ports,
                "message": found.get("message")
                or (
                    f"Something is listening"
                    + (f" on {open_ports}" if open_ports else "")
                    + " but the image API is not ready (or missing --api)."
                ),
            }
        return {
            "ok": False,
            "provider": provider,
            "base_url": found.get("base_url") or listen.get("base_url"),
            "port_open": False,
            "message": found.get("message") or f"{provider} API is not reachable.",
            "tried": found.get("tried"),
        }

    return {"ok": False, "provider": provider, "message": "Unknown provider", "port_open": False}


# Phrases that mean the player only has a partial / non-full view of a subject.
_PARTIAL_VISIBILITY_MARKERS = (
    "silhouette",
    "shadow",
    "outline",
    "glimpse",
    "half-seen",
    "half seen",
    "barely visible",
    "barely seen",
    "through a",
    "through the",
    "behind a wall",
    "behind the wall",
    "through a wall",
    "through the wall",
    "through a crack",
    "through the grate",
    "drain",
    "grate",
    "peep",
    "keyhole",
    "fog",
    "mist",
    "darkness",
    "in the dark",
    "obscured",
    "veiled",
    "hooded",
    "masked",
    "covered face",
    "face hidden",
    "cannot see the face",
    "can't see the face",
    "only hands",
    "only a hand",
    "only feet",
    "only the back",
    "from behind",
    "distant figure",
    "far away",
    "blurred",
    "muffled shape",
    "shape in",
    "figure in the",
    "unseen",
    "out of sight",
    "not fully visible",
    "partially visible",
    "edge of vision",
    "corner of the eye",
)


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def infer_visibility_mode(
    *,
    visibility_note: str = "",
    observed_description: str = "",
    summary: str = "",
    subject: str = "character",
) -> dict[str, Any]:
    """
    Decide how much of a subject the player can actually see.

    Modes:
      full     — clear view; normal face + fullbody allowed
      partial  — limited/obscured view; only generate what is described
      none     — player cannot see them; block generation

    Important: player *backstory* must never be treated as a visibility note.
    Words like fog/shadow/through a in life-story prose were flipping self-portraits
    into partial mode and truncating prompts to four words.
    """
    note = _norm_text(visibility_note)
    observed = _norm_text(observed_description)
    summary_text = _norm_text(summary)
    subject_l = str(subject or "character").strip().lower() or "character"

    # --- Player self-portrait / setup art ---------------------------------
    # Always full unless the *caller* explicitly marks occlusion or invisibility.
    if subject_l == "player":
        none_markers = (
            "not visible",
            "cannot see",
            "can't see",
            "out of sight",
            "unseen",
            "invisible",
            "no visual",
            "player cannot see",
            "off-stage",
            "off stage",
            "heard only",
            "voice only",
            "only a voice",
        )
        if note and any(m in note.lower() for m in none_markers):
            return {
                "mode": "none",
                "visibility_note": note,
                "kinds": [],
                "reason": "Player self-view explicitly marked not visible.",
            }
        if note and any(m in note.lower() for m in _PARTIAL_VISIBILITY_MARKERS):
            return {
                "mode": "partial",
                "visibility_note": note,
                "kinds": ["face"],
                "reason": "Player self-view has an explicit partial-visibility note.",
            }
        return {
            "mode": "full",
            "visibility_note": "",
            "kinds": ["face", "fullbody"],
            "reason": "Self-view / character art — full framing (backstory is not occlusion).",
        }

    # --- NPCs / others ----------------------------------------------------
    blob = f"{note} {observed}".lower()
    # Do not scan life-story `summary` alone for partial markers — too many false positives.
    none_markers = (
        "not visible",
        "cannot see",
        "can't see",
        "out of sight",
        "unseen",
        "invisible",
        "no visual",
        "player cannot see",
        "off-stage",
        "off stage",
        "heard only",
        "voice only",
        "only a voice",
        "behind closed door",
        "another room",
    )
    if note and any(m in note.lower() for m in none_markers):
        return {
            "mode": "none",
            "visibility_note": note or "Subject is not visible to the player.",
            "kinds": [],
            "reason": "Player cannot see this subject.",
        }
    if not note and not observed:
        if subject_l == "npc":
            return {
                "mode": "full",
                "visibility_note": "",
                "kinds": ["face"],
                "reason": "NPC present in scene; no occlusion note.",
            }
        return {
            "mode": "none",
            "visibility_note": "Nothing visual has been observed yet.",
            "kinds": [],
            "reason": "No observed description — do not invent a full appearance.",
        }

    # Explicit visibility_note = caller is framing a glimpse. Observed text soft-matches markers.
    partial = False
    if note:
        partial = True
    elif observed:
        partial = any(m in observed.lower() for m in _PARTIAL_VISIBILITY_MARKERS)

    if partial:
        return {
            "mode": "partial",
            "visibility_note": note
            or observed[:280]
            or "Only a limited glimpse is available to the player.",
            "kinds": ["face"],
            "reason": "Player only has a partial view — art must match the glimpse, not a full character sheet.",
        }

    return {
        "mode": "full",
        "visibility_note": note,
        "kinds": ["face", "fullbody"],
        "reason": "Clear view.",
    }


def assess_character_art_readiness(
    *,
    name: str = "",
    title: str = "",
    known_as: str = "",
    backstory: str = "",
    world_style: str = "",
    extra: str = "",
    age: str = "",
    sex: str = "",
    equipment: list[str] | None = None,
    injuries: list[str] | None = None,
    visibility_note: str = "",
    observed_description: str = "",
    subject: str = "player",
    require_backend: bool = False,
) -> dict[str, Any]:
    """
    Gate character art so we never invent a full look from empty identity,
    and never render full face/body when the player cannot see them.
    """
    missing: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    name = _norm_text(name)
    title = _norm_text(title)
    known_as = _norm_text(known_as)
    backstory = _norm_text(backstory)
    world_style = _norm_text(world_style)
    extra = _norm_text(extra)
    age = _norm_text(age)
    sex = _norm_text(sex)
    observed = _norm_text(observed_description) or backstory
    visibility_note = _norm_text(visibility_note)
    equipment = list(equipment or [])
    injuries = list(injuries or [])

    if require_backend:
        cfg = get_image_config()
        provider = _normalize_provider(cfg.get("provider"))
        if provider == "off":
            missing.append(
                {
                    "code": "backend_off",
                    "title": "Image backend is off",
                    "detail": "Open LLM Settings → Images and set provider to Forge, ComfyUI, or Demo.",
                }
            )

    vis = infer_visibility_mode(
        visibility_note=visibility_note,
        observed_description=observed,
        summary=backstory,
        subject=subject,
    )
    if vis["mode"] == "none":
        missing.append(
            {
                "code": "not_visible",
                "title": "Not visible to the player",
                "detail": vis.get("reason")
                or "Cannot generate appearance until something is actually seen.",
            }
        )

    # Identity: need a name (or alias) for player; NPCs may be "unknown figure".
    if subject == "player":
        if not name and not known_as:
            missing.append(
                {
                    "code": "name",
                    "title": "Name or Known As",
                    "detail": "Set a character name (or public alias) on the Identity step.",
                }
            )
    else:
        if not name and not known_as and not observed:
            missing.append(
                {
                    "code": "subject",
                    "title": "Who is being drawn",
                    "detail": "Need a name or an observed description of the figure.",
                }
            )

    # Visual anchors — enough to avoid a totally empty prompt.
    visual_hits: list[str] = []
    # Optional dedicated look fields (may be passed via kwargs by callers that have them)
    # Keep assess signature stable; extra/appearance often carry them already.
    if sex:
        visual_hits.append("sex")
    if age:
        visual_hits.append("age")
    if backstory and len(backstory) >= 20:
        visual_hits.append("backstory")
    if extra and len(extra) >= 8:
        visual_hits.append("extra")
    if observed and len(observed) >= 12 and observed != backstory:
        visual_hits.append("observed")
    if equipment:
        visual_hits.append("equipment")
    if injuries:
        visual_hits.append("injuries")
    if title and len(title) >= 3:
        visual_hits.append("title")
    if world_style:
        visual_hits.append("world_style")

    if vis["mode"] != "none":
        if subject == "player":
            # Soft bar: sex/age/title/short backstory OR world style is enough.
            # Sex defaults to Unspecified in the UI — do not require it alone.
            body_ok = bool(
                sex
                or age
                or title
                or (backstory and len(backstory) >= 20)
                or (extra and len(extra) >= 8)
                or world_style
                or equipment
            )
            if not body_ok:
                missing.append(
                    {
                        "code": "appearance_cues",
                        "title": "Sex, Age, or World style",
                        "detail": (
                            "On Identity set Sex (Female/Male/…) or Age (e.g. 24), "
                            "or pick a world style on the World step. A short backstory also works."
                        ),
                    }
                )
            if not world_style and not (backstory and len(backstory) >= 40):
                warnings.append(
                    {
                        "code": "no_world_style",
                        "title": "World style empty",
                        "detail": "Art will look more generic without a world style selection.",
                    }
                )
        else:
            # NPC / other: name + race/role/summary/extra is enough for a first look.
            has_npc_cue = bool(
                name
                or known_as
                or title
                or observed
                or extra
                or sex
                or age
                or (backstory and len(backstory) >= 12)
            )
            if not has_npc_cue:
                missing.append(
                    {
                        "code": "observed",
                        "title": "Nothing observed to draw",
                        "detail": "Wait until the player sees them, or pass an observed_description / visibility_note of what is visible.",
                    }
                )
            elif vis["mode"] == "partial" and len(observed or visibility_note or backstory or title) < 8:
                missing.append(
                    {
                        "code": "glimpse_too_thin",
                        "title": "Glimpse is too vague",
                        "detail": "Describe what the player actually sees (e.g. 'person in a drain through a wall').",
                    }
                )

    can_generate = len(missing) == 0
    kinds = list(vis.get("kinds") or [])
    if can_generate and not kinds and vis["mode"] != "none":
        kinds = ["face", "fullbody"] if vis["mode"] == "full" else ["face"]

    return {
        "ok": can_generate,
        "can_generate": can_generate,
        "missing": missing,
        "warnings": warnings,
        "visibility_mode": vis["mode"],
        "visibility_note": vis.get("visibility_note") or visibility_note,
        "recommended_kinds": kinds,
        "visual_hits": visual_hits,
        "subject": subject,
        "message": (
            "Ready to generate."
            if can_generate
            else "Not enough info to generate yet: " + "; ".join(m["title"] for m in missing)
        ),
    }


def _subject_count_tag(sex: str = "") -> str:
    """Classic booru-style subject tag — still the most reliable base for many models."""
    s = str(sex or "").strip().lower()
    if not s:
        return "1person"
    if s in {"f", "female", "woman", "girl"} or s.startswith("female"):
        return "1girl"
    if s in {"m", "male", "man", "boy"} or s.startswith("male"):
        return "1boy"
    return "1person"


def _cap_words(text: str, n: int = 3) -> str:
    return " ".join(str(text or "").split()[:n]).strip()


def _short_setting_tags(world_style: str = "", location: str = "") -> list[str]:
    """Core setting tags from world vibe + start location (≤3 words each)."""
    tags: list[str] = []
    for raw in (world_style, location):
        text = _norm_text(raw)
        if not text:
            continue
        # Prefer comma/slash splits; else take first 2–3 words as one tag.
        chunks = [c.strip() for c in text.replace("/", ",").split(",") if c.strip()]
        if not chunks:
            words = text.split()
            chunks = [" ".join(words[:3])] if words else []
        for c in chunks[:3]:
            w = _cap_words(c, 3).lower()
            if w and w not in tags and w not in {"custom", "none", "n/a"}:
                tags.append(w)
    return tags[:4]


# ---------------------------------------------------------------------------
# Wardrobe: plain category + body zone → filter by image frame
# ---------------------------------------------------------------------------
# Zones describe *where on the body* a look cue sits. Frames only inject cues
# that would actually appear in that crop (portraits never get boots).
# Categories are plain inventory/art classes for players + NPCs alike.

WARDROBE_ZONES = (
    "hair",
    "head",
    "face",
    "neck",
    "torso",
    "arms",
    "hands",
    "waist",
    "legs",
    "feet",
    "held",
    "bag",
    "skip",  # non-visual / not worn
)

WARDROBE_CATEGORIES = (
    "hair",
    "headwear",
    "outerwear",
    "top",
    "bottom",
    "footwear",
    "gloves",
    "belt",
    "accessory",
    "armor",
    "held",
    "bag",
    "consumable",
    "currency",
    "other",
)

# What is visible in each image frame (bust crop vs full figure).
FRAME_VISIBLE_ZONES: dict[str, frozenset[str]] = {
    "face": frozenset({"hair", "head", "face", "neck", "torso"}),
    "partial": frozenset({"hair", "head", "face", "neck", "torso"}),
    "fullbody": frozenset(
        {"hair", "head", "face", "neck", "torso", "arms", "hands", "waist", "legs", "feet", "held", "bag"}
    ),
}

# Keyword → (category, zone). First match wins; order matters (more specific first).
_WARDROBE_KEYWORD_MAP: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("hair", "haired", "braid", "ponytail", "bun"), "hair", "hair"),
    (("hat", "cap", "helmet", "hood", "crown", "helm", "beret"), "headwear", "head"),
    (("glasses", "goggles", "eyepatch", "mask", "scar", "beard", "mustache"), "accessory", "face"),
    (("scarf", "choker", "necklace", "collar pendant", "amulet"), "accessory", "neck"),
    (("gloves", "gauntlets", "mittens"), "gloves", "hands"),
    (("boots", "boot", "shoes", "shoe", "sandals", "sandals", "heels", "slippers", "footwear"), "footwear", "feet"),
    (("trousers", "pants", "leggings", "skirt", "shorts", "jeans", "breeches"), "bottom", "legs"),
    (("belt", "sash", "girdle"), "belt", "waist"),
    (("satchel", "backpack", "rucksack", "pack", "bag", "pouch"), "bag", "bag"),
    (
        (
            "coat",
            "cloak",
            "cape",
            "jacket",
            "robe",
            "robes",
            "gown",
            "mantle",
            "overcoat",
            "parka",
        ),
        "outerwear",
        "torso",
    ),
    (
        (
            "armor",
            "armour",
            "breastplate",
            "cuirass",
            "mail",
            "plate",
            "chestplate",
        ),
        "armor",
        "torso",
    ),
    (
        (
            "tunic",
            "shirt",
            "blouse",
            "vest",
            "apron",
            "dress",
            "kimono",
            "uniform",
            "jumpsuit",
            "overalls",
            "leathers",
            "clothes",
            "clothing",
            "top",
        ),
        "top",
        "torso",
    ),
    (
        ("sword", "knife", "dagger", "axe", "staff", "wand", "lantern", "torch", "tool", "hammer"),
        "held",
        "held",
    ),
    (("rope", "coil"), "held", "waist"),  # often belted; fullbody only
    (("ration", "bread", "food", "water skin", "waterskin", "flask", "drink"), "consumable", "skip"),
    (("coin", "coins", "gold", "copper", "silver", "currency"), "currency", "skip"),
)

_ZONE_ALIASES = {
    "hair": "hair",
    "head": "head",
    "hat": "head",
    "face": "face",
    "neck": "neck",
    "throat": "neck",
    "torso": "torso",
    "chest": "torso",
    "body": "torso",
    "upper": "torso",
    "bust": "torso",
    "shoulders": "torso",
    "arms": "arms",
    "arm": "arms",
    "sleeves": "arms",
    "hands": "hands",
    "hand": "hands",
    "gloves": "hands",
    "waist": "waist",
    "belt": "waist",
    "hips": "waist",
    "legs": "legs",
    "leg": "legs",
    "lower": "legs",
    "feet": "feet",
    "foot": "feet",
    "shoes": "feet",
    "boots": "feet",
    "held": "held",
    "hand-held": "held",
    "carry": "held",
    "bag": "bag",
    "pack": "bag",
    "skip": "skip",
    "none": "skip",
}

_CATEGORY_ALIASES = {
    "hair": "hair",
    "headwear": "headwear",
    "hat": "headwear",
    "outerwear": "outerwear",
    "coat": "outerwear",
    "cloak": "outerwear",
    "top": "top",
    "shirt": "top",
    "bottom": "bottom",
    "pants": "bottom",
    "footwear": "footwear",
    "boots": "footwear",
    "shoes": "footwear",
    "gloves": "gloves",
    "belt": "belt",
    "accessory": "accessory",
    "armor": "armor",
    "armour": "armor",
    "held": "held",
    "weapon": "held",
    "tool": "held",
    "bag": "bag",
    "consumable": "consumable",
    "currency": "currency",
    "other": "other",
    "clothing": "top",
    "clothes": "top",
}


def _split_look_phrases(value: list[str] | str | None) -> list[str]:
    if isinstance(value, list):
        raw_parts = [str(p).strip() for p in value if str(p).strip()]
    elif isinstance(value, str) and value.strip():
        # Prefer semicolon-separated zone lists when present.
        text = value.strip()
        if ";" in text:
            raw_parts = [p.strip() for p in text.split(";") if p.strip()]
        else:
            raw_parts = [p.strip() for p in re.split(r"[,|/]+", text) if p.strip()]
    else:
        raw_parts = []
    cleaned: list[str] = []
    for part in raw_parts:
        text = re.sub(r"\s+", " ", part).strip(" .")
        if text:
            cleaned.append(text)
    return cleaned


def _infer_wardrobe_from_label(label: str) -> tuple[str, str]:
    """Return (category, zone) from free-text clothing/item words."""
    low = re.sub(r"\([^)]*\)", " ", label).lower()
    low = re.sub(r"\s+", " ", low).strip()
    for keys, category, zone in _WARDROBE_KEYWORD_MAP:
        if any(k in low for k in keys):
            return category, zone
    # Short wearable phrases still default to torso top
    words = low.split()
    if 1 <= len(words) <= 5:
        return "other", "torso"
    return "other", "skip"


def _parse_wardrobe_entry(raw: str) -> dict[str, str] | None:
    """
    Parse one wardrobe entry into {label, category, zone, prompt}.

    Supported shapes (player + NPC appearance):
      travel-stained coat
      torso: travel-stained coat
      outerwear/torso: travel-stained coat
      [torso] travel-stained coat
      [outerwear|torso] travel-stained coat
    """
    text = str(raw or "").strip()
    if not text:
        return None
    category = ""
    zone = ""
    label = text

    bracket = re.match(r"^\[([^\]]+)\]\s*(.+)$", text)
    if bracket:
        meta, label = bracket.group(1).strip(), bracket.group(2).strip()
        parts = [p.strip().lower() for p in re.split(r"[|/:,]+", meta) if p.strip()]
        for p in parts:
            if p in _ZONE_ALIASES and not zone:
                zone = _ZONE_ALIASES[p]
            elif p in _CATEGORY_ALIASES and not category:
                category = _CATEGORY_ALIASES[p]
    else:
        # category/zone: label  OR  zone: label
        m = re.match(r"^([a-zA-Z][a-zA-Z0-9_ \-]{0,24})\s*[/|]\s*([a-zA-Z][a-zA-Z0-9_ \-]{0,24})\s*:\s*(.+)$", text)
        if m:
            a, b, label = m.group(1).strip().lower(), m.group(2).strip().lower(), m.group(3).strip()
            if a in _CATEGORY_ALIASES:
                category = _CATEGORY_ALIASES[a]
            elif a in _ZONE_ALIASES:
                zone = _ZONE_ALIASES[a]
            if b in _ZONE_ALIASES:
                zone = _ZONE_ALIASES[b]
            elif b in _CATEGORY_ALIASES and not category:
                category = _CATEGORY_ALIASES[b]
        else:
            m2 = re.match(r"^([a-zA-Z][a-zA-Z0-9_ \-]{0,24})\s*:\s*(.+)$", text)
            if m2:
                key, label = m2.group(1).strip().lower(), m2.group(2).strip()
                if key in _ZONE_ALIASES:
                    zone = _ZONE_ALIASES[key]
                elif key in _CATEGORY_ALIASES:
                    category = _CATEGORY_ALIASES[key]

    label = re.sub(r"\s+", " ", label).strip(" .")
    if not label:
        return None
    # Strip leftover parens clutter for prompt words
    prompt_label = re.sub(r"\([^)]*\)", " ", label)
    prompt_label = re.sub(r"\s+", " ", prompt_label).strip()
    if not prompt_label:
        return None

    inferred_cat, inferred_zone = _infer_wardrobe_from_label(prompt_label)
    if not category:
        category = inferred_cat
    if not zone:
        zone = inferred_zone
    # Consumables/currency never paint
    if category in {"consumable", "currency"}:
        zone = "skip"
    if zone not in WARDROBE_ZONES:
        zone = "torso"
    if category not in WARDROBE_CATEGORIES:
        category = "other"

    return {
        "label": prompt_label[:80],
        "category": category,
        "zone": zone,
        "prompt": _cap_words(prompt_label, 5).lower(),
    }


def parse_wardrobe(
    *sources: list[str] | str | None,
) -> list[dict[str, str]]:
    """Parse free-text / lists of look + gear into structured wardrobe entries."""
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in sources:
        for phrase in _split_look_phrases(source):
            entry = _parse_wardrobe_entry(phrase)
            if not entry:
                continue
            key = f"{entry['zone']}|{entry['prompt']}"
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
    return entries


def wardrobe_tags_for_frame(
    entries: list[dict[str, str]],
    *,
    kind: str = "face",
    visibility_mode: str = "full",
    max_tags: int | None = None,
) -> list[str]:
    """
    Pick prompt tags whose body zone is visible in this frame.
    Portrait/face: hair + head + face + neck + torso only (no boots/legs).
    Full body: all wearable zones. Partial: bust zones only.
    """
    kind_key = "fullbody" if str(kind).lower() in {"fullbody", "body", "full"} else "face"
    mode = str(visibility_mode or "full").lower().strip() or "full"
    if mode == "partial":
        frame = "partial"
    elif kind_key == "fullbody":
        frame = "fullbody"
    else:
        frame = "face"
    visible = FRAME_VISIBLE_ZONES.get(frame) or FRAME_VISIBLE_ZONES["face"]
    if max_tags is None:
        max_tags = 5 if frame == "fullbody" else 3

    # Prefer: hair → head → face → neck → torso → arms → hands → waist → legs → feet → bag → held
    zone_order = {
        "hair": 0,
        "head": 1,
        "face": 2,
        "neck": 3,
        "torso": 4,
        "arms": 5,
        "hands": 6,
        "waist": 7,
        "legs": 8,
        "feet": 9,
        "bag": 10,
        "held": 11,
    }
    ranked = sorted(
        (e for e in entries if e.get("zone") in visible and e.get("zone") != "skip"),
        key=lambda e: (zone_order.get(str(e.get("zone")), 50), str(e.get("category") or "")),
    )
    tags: list[str] = []
    seen: set[str] = set()
    for entry in ranked:
        prompt = str(entry.get("prompt") or "").strip()
        if not prompt or prompt in seen:
            continue
        # Face frame: skip pure held tools (knives) unless they are clearly torso-visible outerwear
        if frame in {"face", "partial"} and entry.get("zone") in {"held", "bag", "waist"}:
            continue
        seen.add(prompt)
        tags.append(prompt)
        if len(tags) >= max_tags:
            break
    return tags


def _title_wardrobe_fallback(title: str) -> list[dict[str, str]]:
    title_l = _norm_text(title).lower()
    title_map = (
        ("knight", "plate armor"),
        ("scholar", "scholar robes"),
        ("mage", "mage robes"),
        ("wizard", "wizard robes"),
        ("cartograph", "travel coat"),
        ("courier", "travel cloak"),
        ("assassin", "dark leathers"),
        ("noble", "fine coat"),
        ("soldier", "military uniform"),
        ("priest", "cleric robes"),
        ("hunter", "hunter gear"),
        ("thief", "street leathers"),
        ("ranger", "ranger gear"),
        ("bard", "stage clothes"),
        ("merchant", "trade coat"),
        ("pirate", "sea coat"),
        ("monk", "simple robes"),
        ("alchemist", "lab coat"),
    )
    for key, outfit in title_map:
        if key in title_l:
            entry = _parse_wardrobe_entry(outfit)
            return [entry] if entry else []
    return []


def _clothing_tags(
    *,
    title: str = "",
    equipment: list[str] | str | None = None,
    extra: str = "",
    appearance: str = "",
    kind: str = "face",
    visibility_mode: str = "full",
) -> list[str]:
    """
    Clothing / worn-look tags filtered by body zone for the image frame.
    Shared by player setup art and NPC portraits.
    """
    entries = parse_wardrobe(appearance, extra, equipment)
    if not entries:
        entries = _title_wardrobe_fallback(title)
    if not entries:
        blob = f"{extra} {appearance}".lower()
        if "cloak" in blob:
            entries = parse_wardrobe("torso: worn cloak")
        elif "armor" in blob or "armour" in blob:
            entries = parse_wardrobe("torso: light armor")
        elif "robe" in blob:
            entries = parse_wardrobe("torso: simple robes")
    return wardrobe_tags_for_frame(entries, kind=kind, visibility_mode=visibility_mode)


def _clothing_short(
    *,
    title: str = "",
    equipment: list[str] | str | None = None,
    extra: str = "",
    appearance: str = "",
    kind: str = "face",
    visibility_mode: str = "full",
) -> str:
    """Backward-compatible single string of clothing tags."""
    return ", ".join(
        _clothing_tags(
            title=title,
            equipment=equipment,
            extra=extra,
            appearance=appearance,
            kind=kind,
            visibility_mode=visibility_mode,
        )
    )


def _hair_short(extra: str = "", backstory: str = "") -> str:
    """Optional hair cue from free text — ≤3 words (e.g. long silver hair)."""
    blob = f"{extra} {backstory}".lower()
    colors = (
        "white",
        "silver",
        "black",
        "brown",
        "blonde",
        "blond",
        "red",
        "auburn",
        "blue",
        "green",
        "pink",
        "purple",
        "grey",
        "gray",
    )
    lengths = ("long", "short", "wavy", "curly", "straight")
    for c in colors:
        if f"{c}-haired" in blob or f"{c} haired" in blob:
            # Prefer length + colour when both appear
            for ln in lengths:
                if ln in blob:
                    return f"{ln} {c} hair"
            return f"{c} hair"
        if f"{c} hair" in blob:
            for ln in lengths:
                if f"{ln} {c} hair" in blob or f"{ln}, {c}" in blob or f"{ln} {c}" in blob:
                    return f"{ln} {c} hair"
            # "long … silver hair" with words between
            for ln in lengths:
                if ln in blob:
                    return f"{ln} {c} hair"
            return f"{c} hair"
    if "long hair" in blob:
        return "long hair"
    if "short hair" in blob:
        return "short hair"
    return ""


def _extra_detail_tags(
    extra: str = "",
    *,
    already: set[str] | None = None,
    allow_scene: bool = False,
) -> list[str]:
    """
    Tiny leftover cues from the free-text art box.
    Portrait: character-only crumbs. Full body: room for one small scene note.
    Never dump prose — max one short tag, ≤3 words.
    """
    text = _norm_text(extra)
    if not text:
        return []
    already = {a.lower() for a in (already or set())}
    # Work per comma-chunk so stripping hair from chunk 1 doesn't kill chunk 2
    hair_tokens = {
        "long",
        "short",
        "wavy",
        "curly",
        "straight",
        "white",
        "silver",
        "black",
        "brown",
        "blonde",
        "blond",
        "red",
        "auburn",
        "blue",
        "green",
        "pink",
        "purple",
        "grey",
        "gray",
        "hair",
        "haired",
    }
    scene_words = {
        "neon",
        "city",
        "lab",
        "laboratory",
        "winter",
        "forest",
        "street",
        "rain",
        "snow",
        "ruins",
        "temple",
        "tavern",
        "dock",
        "ship",
        "castle",
        "alley",
        "sky",
        "space",
        "fire",
        "magic",
    }
    for raw_chunk in text.replace("/", ",").split(","):
        chunk = raw_chunk.strip().lower()
        if not chunk:
            continue
        # Drop whole chunks that are already represented (e.g. "pink hair")
        if chunk in already:
            continue
        cleaned = chunk
        for phrase in sorted(already, key=len, reverse=True):
            if phrase and phrase in cleaned:
                cleaned = cleaned.replace(phrase, " ")
        # Remove bare hair tokens left after folding into a longer hair tag
        cleaned_words = [w for w in cleaned.split() if w not in hair_tokens]
        cleaned = " ".join(cleaned_words).strip(" ,.;:-")
        if not cleaned:
            continue
        tag = _cap_words(cleaned, 3).lower()
        if not tag or tag in already:
            continue
        words = set(tag.split())
        # Scene crumbs only when the frame has room (full body)
        if words & scene_words and not allow_scene:
            continue
        return [tag]
    return []


def _facial_feature_tags(facial_features: str = "", *, kind: str = "face") -> list[str]:
    """
    Bust-visible face details for portraits and full body.
    Keeps short phrase tags (eyes, freckles, scars, jaw) — not clothing.
    """
    kind_key = "fullbody" if str(kind).lower() in {"fullbody", "body", "full"} else "face"
    # Full body still benefits from a couple of face anchors for consistency.
    max_tags = 4 if kind_key == "face" else 3
    tags: list[str] = []
    seen: set[str] = set()
    for phrase in _split_look_phrases(facial_features):
        # Skip if it looks like wardrobe (coat/boots) — those belong in appearance.
        low = phrase.lower()
        if any(
            w in low
            for w in (
                "coat",
                "cloak",
                "boot",
                "shoe",
                "pants",
                "trouser",
                "armor",
                "tunic",
                "dress",
                "jacket",
            )
        ):
            continue
        clean = _cap_words(phrase, 5).lower()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        tags.append(clean)
        if len(tags) >= max_tags:
            break
    return tags


def _explicit_hair_tag(hair: str = "", *, extra: str = "", appearance: str = "", backstory: str = "") -> str:
    """Prefer the dedicated hair field; fall back to free-text extraction."""
    explicit = _norm_text(hair)
    if explicit:
        # Ensure the word "hair" is present for models that key on it.
        low = explicit.lower()
        if "hair" not in low and "braid" not in low and "ponytail" not in low and "bun" not in low:
            explicit = f"{explicit} hair"
        return _cap_words(explicit, 5).lower()
    return _hair_short(f"{extra} {appearance}", backstory)


def build_portrait_prompt(
    *,
    name: str = "",
    title: str = "",
    known_as: str = "",
    backstory: str = "",
    world_style: str = "",
    extra: str = "",
    style: str = "",
    equipment: list[str] | str | None = None,
    hair: str = "",
    facial_features: str = "",
    appearance: str = "",
    level: int | str | None = None,
    injuries: list[str] | str | None = None,
    age: str = "",
    sex: str = "",
    visibility_mode: str = "full",
    visibility_note: str = "",
    observed_description: str = "",
    kind: str = "face",
    location: str = "",
) -> str:
    """
    Simple ordered tag prompt — face and body share the same skeleton.

    Paragraph order (comma-separated):
      1. core     — 1girl/1boy, setting tags (location / vibe)
      2. character — pose, hair, facial features, zone-filtered clothes
      3. framing  — (portrait:1.5)  OR  (full body:1.7)
      4. detail   — optional tiny extra (full body may keep a small scene crumb)
      5. LoRAs    — appended later by build_character_prompt_pack

    Full body relies on (full body:1.7) in the positive — no “legs out of frame” negatives
    (those can force odd crops). Only pose + image-type differ between face and fullbody.
    Users refine weights in the engine box (Ctrl+↑/↓).
    """
    mode = str(visibility_mode or "full").lower().strip() or "full"
    kind_key = "fullbody" if str(kind).lower() in {"fullbody", "body", "full"} else "face"
    note = _norm_text(visibility_note)
    observed = _norm_text(observed_description)
    # Clothes only here; hair/face come from dedicated fields.
    appearance_text = _norm_text(appearance) or ""
    # NPCs often store full look in observed_description — still usable as wardrobe.
    look_blob = appearance_text or observed

    if mode == "none":
        return "no visible subject"

    # Shared lean skeleton for full + partial (partial only adds a short cue; never chops life-story prose).
    parts: list[str] = []

    # --- 1. core: subject + setting ---
    parts.append(_subject_count_tag(sex))
    parts.extend(_short_setting_tags(world_style, location))

    # --- 2. character: pose → hair → face → zone-filtered clothing ---
    if mode == "partial":
        parts.append("partial view")
    elif kind_key == "face":
        parts.append("looking at viewer")
    else:
        parts.append("standing")
    hair_tag = _explicit_hair_tag(hair, extra=extra, appearance=f"{look_blob} {facial_features}", backstory=backstory)
    if hair_tag:
        parts.append(hair_tag)
    for face_tag in _facial_feature_tags(facial_features, kind=kind_key):
        if face_tag not in {p.lower() for p in parts}:
            parts.append(face_tag)
    # Clothing tags: only zones visible in this frame (portrait never gets feet/legs).
    # Do not re-inject hair from wardrobe if we already have an explicit hair field.
    for clothes in _clothing_tags(
        title=title,
        equipment=equipment,
        extra=extra,
        appearance=look_blob,
        kind=kind_key,
        visibility_mode=mode,
    ):
        if hair_tag and clothes == hair_tag:
            continue
        if "hair" in clothes and hair_tag:
            continue
        parts.append(clothes)

    # --- 3. image type / framing ---
    if mode == "partial":
        # Glimpse still uses portrait framing; never invent full body sheets.
        parts.append("(portrait:1.5)")
        # Only use an explicit visual note — not a 4-word slice of backstory.
        cue = note
        if cue:
            # Drop prose; keep ≤3 words of visual framing
            short_cue = _cap_words(cue, 3).lower()
            if short_cue and short_cue not in {p.lower() for p in parts}:
                # Skip if it looks like a life-story opener ("born on the…")
                if not short_cue.startswith(("born ", "raised ", "after ", "once ", "they ")):
                    parts.append(short_cue)
    elif kind_key == "face":
        parts.append("(portrait:1.5)")
    else:
        # Strong full-figure framing — face-ref img2img used to collapse to bust shots.
        parts.append("(full body:1.7)")
        parts.append("full body shot")
        parts.append("head to toe")
        parts.append("entire body in frame")
        parts.append("standing full figure")
        parts.append("wide shot")

    # --- 4. tiny optional detail (no big background inventing on portraits) ---
    if mode != "partial":
        for tag in _extra_detail_tags(
            extra,
            already=set(parts),
            allow_scene=(kind_key == "fullbody"),
        ):
            parts.append(tag)

    # Drop empties / dupes while preserving order
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        key = p.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p.strip())
    return ", ".join(out)


def format_lora_tags(loras: list[Any] | None) -> str:
    """Turn [{name, weight}] into A1111/Forge prompt tags."""
    tags: list[str] = []
    for entry in loras or []:
        if isinstance(entry, str):
            name = entry.strip()
            weight = 1.0
        elif isinstance(entry, dict):
            name = str(entry.get("name") or entry.get("alias") or "").strip()
            try:
                weight = float(entry.get("weight") if entry.get("weight") is not None else 1.0)
            except (TypeError, ValueError):
                weight = 1.0
        else:
            continue
        if not name:
            continue
        # Already a tag
        if name.startswith("<lora:"):
            tags.append(name)
            continue
        weight = max(0.05, min(2.0, weight))
        tags.append(f"<lora:{name}:{weight:g}>")
    return " ".join(tags)


def _data_url_to_b64(data_url: str) -> str:
    """Return raw base64 (no data: prefix). Forge ControlNet crashes on wrong types."""
    raw = str(data_url or "").strip()
    if not raw:
        return ""
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1].strip()
    # Some clients leave whitespace/newlines in long data URLs
    return "".join(raw.split())


# Negatives that fight portrait/bust composition when generating full body from a face ref.
_FULLBODY_FRAME_NEGATIVES = (
    "portrait, close-up, headshot, bust shot, upper body only, head and shoulders, "
    "cropped legs, legs out of frame, face only, tight crop, selfie, passport photo, "
    "zoomed in face, mugshot, bust portrait, half body"
)


def _composite_face_ref_for_fullbody(
    face_data_or_b64: str,
    *,
    width: int,
    height: int,
) -> str:
    """
    Place a face portrait into the *upper* portion of a tall canvas instead of
    stretching it full-frame. Stretching a face crop to 576×768 locks img2img
    into portrait composition no matter how hard you prompt full body.

    Returns raw base64 PNG (no data: prefix). Empty string on failure.
    """
    b64 = _data_url_to_b64(face_data_or_b64)
    if not b64:
        return ""
    try:
        from io import BytesIO

        from PIL import Image

        raw = base64.b64decode(b64)
        face = Image.open(BytesIO(raw)).convert("RGB")
        tw = max(64, int(width or 576))
        th = max(64, int(height or 768))
        fw0, fh0 = face.size
        # Already a tall fullbody-shaped canvas (e.g. previous composite) — do not nest again.
        if fh0 >= fw0 * 1.15 and abs(fw0 - tw) <= 48 and abs(fh0 - th) <= 64:
            if (fw0, fh0) != (tw, th):
                face = face.resize((tw, th), Image.Resampling.LANCZOS)
            out_buf = BytesIO()
            face.save(out_buf, format="PNG", optimize=True)
            return base64.b64encode(out_buf.getvalue()).decode("ascii")
        # Soft neutral canvas (not pure black — some models treat black as void).
        canvas = Image.new("RGB", (tw, th), (42, 44, 48))
        # Face occupies ~top 28–36% height, centered — room for torso/legs below.
        max_face_h = max(64, int(th * 0.34))
        max_face_w = max(64, int(tw * 0.72))
        fw, fh = face.size
        scale = min(max_face_w / max(1, fw), max_face_h / max(1, fh), 1.35)
        nw = max(32, int(fw * scale))
        nh = max(32, int(fh * scale))
        face_r = face.resize((nw, nh), Image.Resampling.LANCZOS)
        x = (tw - nw) // 2
        y = max(8, int(th * 0.04))
        canvas.paste(face_r, (x, y))
        # Mild downward fade under the face so the model invents body, not a hard cut.
        try:
            from PIL import ImageDraw

            fade = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            draw = ImageDraw.Draw(fade)
            fade_top = y + nh - 8
            fade_bot = min(th, fade_top + max(24, nh // 3))
            for row in range(fade_top, fade_bot):
                t = (row - fade_top) / max(1, fade_bot - fade_top)
                alpha = int(40 * (1.0 - t))
                draw.line([(0, row), (tw, row)], fill=(42, 44, 48, alpha))
            canvas = Image.alpha_composite(canvas.convert("RGBA"), fade).convert("RGB")
        except Exception:
            pass
        out = BytesIO()
        canvas.save(out, format="PNG", optimize=True)
        return base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        return ""


def _strip_portrait_framing_tokens(prompt: str) -> str:
    """Remove strong portrait/bust tokens that poison full-body gens when primary is shared."""
    text = str(prompt or "")
    if not text:
        return ""
    # Drop common portrait framing phrases (weight syntax included).
    patterns = [
        r"\(\s*portrait\s*:[^)]+\)",
        r"\(\s*close[- ]?up\s*:[^)]+\)",
        r"\(\s*head\s*and\s*shoulders\s*:[^)]+\)",
        r"\bportrait\b",
        r"\bclose[- ]?up\b",
        r"\bhead\s*and\s*shoulders\b",
        r"\bbust\s*shot\b",
        r"\bheadshot\b",
        r"\bpassport\s*photo\b",
        r"\bmugshot\b",
        r"\bselfie\b",
        r"\bupper\s*body\s*only\b",
    ]
    cleaned = text
    for pat in patterns:
        cleaned = re.sub(pat, " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*,\s*,+", ", ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" ,")


def _fullbody_negative(negative: str) -> str:
    """Append framing negatives that discourage portrait crops."""
    neg = str(negative or "").strip()
    extra = _FULLBODY_FRAME_NEGATIVES
    # Avoid doubling if user already pasted them.
    low = neg.lower()
    bits = [p.strip() for p in extra.split(",") if p.strip() and p.strip().lower() not in low]
    if not bits:
        return neg
    add = ", ".join(bits)
    return f"{neg}, {add}" if neg else add


def generate_image(
    *,
    prompt: str,
    negative_prompt: str | None = None,
    width: int | None = None,
    height: int | None = None,
    steps: int | None = None,
    cfg_scale: float | None = None,
    seed: int | None = None,
    purpose: str = "generic",
    loras: list[Any] | None = None,
    init_image: str | None = None,
    denoising_strength: float | None = None,
    apply_primary: bool = True,
    apply_loras: bool = True,
    face_lock_image: str | None = None,
    consistency_mode: str | None = None,
) -> dict[str, Any]:
    """
    Generate one image. Returns:
      ok, provider, mime, image_base64, data_url, path (if saved), seed, elapsed_ms, error?

    init_image: data URL or raw base64 — when set, Forge uses img2img (light lock).
    face_lock_image: reference face for strong ControlNet InstantID / IP-Adapter when available.
    apply_primary / apply_loras: set False when prompt is already the final engine string.
    """
    from app.gpu_gate import gpu_session

    cfg = get_image_config()
    provider = _normalize_provider(cfg.get("provider"))
    if provider == "off":
        return {
            "ok": False,
            "provider": "off",
            "error": "Image backend is off. Set provider to demo, forge, or comfyui in Image settings.",
        }
    prompt = str(prompt or "").strip()
    purpose_l = str(purpose or "").lower()
    is_body = any(k in purpose_l for k in ("fullbody", "full body", "character_fullbody", "character_body"))
    if apply_primary:
        primary = str(cfg.get("primary_prompt") or "").strip()
        if is_body:
            primary = _strip_portrait_framing_tokens(primary)
        if primary and primary not in prompt:
            prompt = f"{primary}, {prompt}" if prompt else primary
    if is_body:
        # Even engine overrides can still carry a leftover portrait weight from older rebuilds.
        prompt = _strip_portrait_framing_tokens(prompt) if "(portrait" in prompt.lower() or "head and shoulders" in prompt.lower() else prompt
        # Ensure full-body framing tokens survive engine edits.
        low_p = prompt.lower()
        if "full body" not in low_p and "fullbody" not in low_p:
            prompt = f"(full body:1.7), full body shot, head to toe, {prompt}" if prompt else "(full body:1.7), full body shot, head to toe"
    if apply_loras:
        lora_tags = format_lora_tags(loras)
        if lora_tags:
            prompt = f"{prompt}, {lora_tags}" if prompt else lora_tags
    if not prompt:
        return {"ok": False, "provider": provider, "error": "Prompt is empty."}
    if is_body and negative_prompt is not None:
        negative_prompt = _fullbody_negative(str(negative_prompt))
    elif is_body and negative_prompt is None:
        # Will be filled from cfg later — mark via sentinel handled in body
        pass

    try:
        with gpu_session("image", wait=True, timeout=float(os.getenv("AI_RPG_GPU_WAIT_TIMEOUT", "900"))):
            return _generate_image_body(
                cfg=cfg,
                provider=provider,
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                steps=steps,
                cfg_scale=cfg_scale,
                seed=seed,
                purpose=purpose,
                init_image=init_image,
                denoising_strength=denoising_strength,
                face_lock_image=face_lock_image,
                consistency_mode=consistency_mode,
            )
    except TimeoutError as exc:
        return {"ok": False, "provider": provider, "error": str(exc)}
    except RuntimeError as exc:
        return {"ok": False, "provider": provider, "error": str(exc)}


def _generate_image_body(
    *,
    cfg: dict[str, Any],
    provider: str,
    prompt: str,
    negative_prompt: str | None,
    width: int | None,
    height: int | None,
    steps: int | None,
    cfg_scale: float | None,
    seed: int | None,
    purpose: str,
    init_image: str | None = None,
    denoising_strength: float | None = None,
    face_lock_image: str | None = None,
    consistency_mode: str | None = None,
) -> dict[str, Any]:
    width = int(width or cfg.get("default_width") or 512)
    height = int(height or cfg.get("default_height") or 512)
    steps = int(steps or cfg.get("default_steps") or 20)
    cfg_scale = float(cfg_scale if cfg_scale is not None else cfg.get("default_cfg") or 7)
    negative = (
        negative_prompt
        if negative_prompt is not None
        else str(cfg.get("negative_prompt") or "")
    )
    primary_neg = str(cfg.get("primary_negative") or "").strip()
    if primary_neg and primary_neg not in (negative or ""):
        negative = f"{negative}, {primary_neg}" if negative else primary_neg
    if seed is None:
        seed = int(time.time() * 1000) % (2**31 - 1)
    timeout = int(cfg.get("timeout_seconds") or 180)
    started = time.time()
    init_b64 = _data_url_to_b64(init_image or "")

    presets = load_image_presets()
    shared = presets.get("shared") if isinstance(presets.get("shared"), dict) else {}
    sampler_name = str(
        cfg.get("forge_sampler") or shared.get("sampler_name") or "Euler a"
    ).strip() or "Euler a"
    if not negative and shared.get("negative_prompt"):
        negative = str(shared.get("negative_prompt") or "")
    purpose_l0 = str(purpose or "").lower()
    is_body_purpose0 = any(k in purpose_l0 for k in ("fullbody", "full body", "body"))
    if is_body_purpose0:
        negative = _fullbody_negative(negative)
    try:
        if provider == "demo":
            result = _generate_demo_image(
                width=width,
                height=height,
                prompt=prompt,
                purpose=purpose,
                seed=int(seed),
            )
        elif provider == "forge":
            found = discover_backend_base_url("forge", cfg, persist=True)
            if not found.get("ok"):
                return {
                    "ok": False,
                    "provider": "forge",
                    "error": found.get("message")
                    or "Forge API not reachable (check port — often 7861 if 7860 is busy).",
                }
            denoise = (
                float(denoising_strength)
                if denoising_strength is not None
                else float(cfg.get("fullbody_ref_denoise") or 0.88)
            )
            alwayson = None
            prefer_cn = False
            lock_b64 = _data_url_to_b64(face_lock_image or "")
            # Prefer light img2img for face continuity. InstantID ControlNet API is unstable
            # on Forge (y is None / shape errors). Only attempt CN when a non-InstantID unit exists.
            cons_cfg = dict(cfg)
            if consistency_mode:
                cons_cfg["character_consistency"] = consistency_mode
            resolved = resolve_character_consistency_mode(cons_cfg)

            purpose_l = str(purpose or "").lower()
            is_body_purpose = any(k in purpose_l for k in ("fullbody", "full body", "body"))
            # Face used as raw init for body → composite onto tall canvas (never stretch bust to full frame).
            if is_body_purpose and init_b64 and not lock_b64:
                # init may already be a face portrait from generate_character_set
                composited = _composite_face_ref_for_fullbody(init_b64, width=width, height=height)
                if composited:
                    init_b64 = composited
                    denoise = max(float(denoise), 0.84)
            elif is_body_purpose and lock_b64 and not init_b64:
                composited = _composite_face_ref_for_fullbody(lock_b64, width=width, height=height)
                if composited and (
                    resolved.get("use_light_img2img")
                    or resolved.get("mode") == "light"
                ):
                    init_b64 = composited
                    denoise = max(float(denoise), 0.84)
            ref_b64_for_fallback = lock_b64 or init_b64
            ad_wants_face_ref = (
                bool(cfg.get("adetailer_enable"))
                and bool(cfg.get("adetailer_use_face_ref", True))
                and bool(lock_b64 or init_b64)
            )
            # ADetailer has no external face-image API — identity must already be in the canvas.
            # When AD + face ref: force light face lock even if global consistency is Off.
            if ad_wants_face_ref and (is_body_purpose or not init_b64):
                if resolved.get("mode") == "off" or not (
                    resolved.get("use_light_img2img") or resolved.get("use_strong")
                ):
                    resolved = {
                        **resolved,
                        "mode": "light",
                        "use_light_img2img": True,
                        "use_strong": False,
                        "fallback_reason": "ADetailer face-ref needs light face lock on the main gen.",
                    }

            # Default light path: face ref as init — for body always composite first.
            if lock_b64 and (
                resolved.get("use_light_img2img")
                or resolved.get("mode") == "light"
                or not resolved.get("use_strong")
            ):
                if not init_b64:
                    if is_body_purpose:
                        composited = _composite_face_ref_for_fullbody(
                            lock_b64, width=width, height=height
                        )
                        init_b64 = composited or lock_b64
                        if composited:
                            denoise = max(float(denoise), 0.84)
                    else:
                        init_b64 = lock_b64
            if resolved.get("use_strong") and lock_b64:
                probe = resolved.get("probe") or probe_character_lock(cfg)
                weight = float(cfg.get("character_lock_weight") or 0.65)
                units = _pick_face_lock_units(probe, weight, lock_b64)
                alwayson = _controlnet_alwayson_args(units)
                if alwayson:
                    prefer_cn = True
                    init_b64 = ""  # CN path only
                else:
                    prefer_cn = False
                    alwayson = None
                    if not init_b64:
                        init_b64 = lock_b64
                    resolved = {
                        **resolved,
                        "mode": "light",
                        "use_strong": False,
                        "use_light_img2img": True,
                        "fallback_reason": "No API-safe non-InstantID ControlNet face unit; using img2img ref.",
                    }
            forge_base = str(found.get("base_url") or cfg.get("forge_base_url") or DEFAULT_FORGE_URL)

            adetailer_scripts = _adetailer_alwayson_args(
                cfg,
                purpose=purpose,
                prompt=prompt,
                negative=negative,
                face_ref_b64=lock_b64 if ad_wants_face_ref else None,
            )

            def _forge_call(*, use_cn: bool, init: str, always: dict | None) -> dict[str, Any]:
                scripts = _merge_alwayson_scripts(
                    always if use_cn else None,
                    adetailer_scripts,
                )
                return _generate_forge(
                    base_url=forge_base,
                    prompt=prompt,
                    negative_prompt=negative,
                    width=width,
                    height=height,
                    steps=steps,
                    cfg_scale=cfg_scale,
                    seed=int(seed),
                    timeout=timeout,
                    sampler_name=sampler_name,
                    scheduler=str(cfg.get("forge_scheduler") or "Automatic"),
                    checkpoint=str(cfg.get("forge_checkpoint") or ""),
                    vae=str(cfg.get("forge_vae") or ""),
                    clip_skip=int(cfg.get("forge_clip_skip") or 1),
                    restore_faces=bool(cfg.get("forge_restore_faces")),
                    tiling=bool(cfg.get("forge_tiling")),
                    enable_hr=bool(cfg.get("forge_enable_hr")) and not init and not use_cn,
                    hr_scale=float(cfg.get("forge_hr_scale") or 1.5),
                    hr_upscaler=str(cfg.get("forge_hr_upscaler") or "Latent"),
                    denoising_strength=denoise,
                    init_images=[init] if init else None,
                    alwayson_scripts=scripts,
                    prefer_txt2img_with_controlnet=bool(use_cn),
                )

            try:
                result = _forge_call(use_cn=prefer_cn, init=init_b64 if not prefer_cn else "", always=alwayson)
            except Exception as cn_exc:
                err_l = str(cn_exc).lower()
                # ControlNet failure → light img2img (keep ADetailer if enabled).
                if prefer_cn and ref_b64_for_fallback:
                    result = _forge_call(use_cn=False, init=ref_b64_for_fallback, always=None)
                    prefer_cn = False
                    result["controlnet_fallback"] = "light_img2img"
                    result["controlnet_error"] = str(cn_exc)[:400]
                    resolved = {
                        **resolved,
                        "mode": "light",
                        "use_strong": False,
                        "fallback_reason": str(cn_exc)[:200],
                    }
                elif adetailer_scripts and ("adetailer" in err_l or "a detail" in err_l or "500" in err_l):
                    # Retry once without ADetailer if extension misbehaves
                    adetailer_scripts = None
                    result = _forge_call(
                        use_cn=prefer_cn,
                        init=init_b64 if not prefer_cn else (ref_b64_for_fallback or ""),
                        always=alwayson if prefer_cn else None,
                    )
                    result["adetailer_fallback"] = "disabled_after_error"
                    result["adetailer_error"] = str(cn_exc)[:300]
                elif ref_b64_for_fallback and not init_b64:
                    result = _forge_call(use_cn=False, init=ref_b64_for_fallback, always=None)
                    result["controlnet_fallback"] = "light_img2img"
                else:
                    raise
            result["consistency_mode"] = resolved.get("mode")
            result["consistency_strong"] = bool(prefer_cn)
            result["adetailer"] = bool(adetailer_scripts)
            result["adetailer_face_ref"] = bool(ad_wants_face_ref and lock_b64)
            if ad_wants_face_ref and lock_b64:
                result["adetailer_face_ref_note"] = (
                    "ADetailer has no external face-image field; face was locked into the main "
                    "gen (light img2img), then ADetailer refined that face with identity-aware settings."
                )
        elif provider == "comfyui":
            found = discover_backend_base_url("comfyui", cfg, persist=True)
            if not found.get("ok"):
                return {
                    "ok": False,
                    "provider": "comfyui",
                    "error": found.get("message") or "ComfyUI API not reachable.",
                }
            result = _generate_comfy(
                base_url=str(found.get("base_url") or cfg.get("comfy_base_url") or DEFAULT_COMFY_URL),
                prompt=prompt,
                negative_prompt=negative,
                width=width,
                height=height,
                steps=steps,
                cfg_scale=cfg_scale,
                seed=int(seed),
                checkpoint=str(cfg.get("comfy_checkpoint") or ""),
                workflow_name=str(cfg.get("comfy_workflow") or "txt2img_api.json"),
                timeout=timeout,
                sampler_name=str(cfg.get("comfy_sampler_name") or "euler"),
                scheduler=str(cfg.get("comfy_scheduler") or "normal"),
            )
        else:
            return {"ok": False, "provider": provider, "error": f"Unsupported provider: {provider}"}
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "error": str(exc),
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    raw_b64 = result.get("image_base64") or ""
    mime = result.get("mime") or "image/png"
    path = ""
    try:
        path = _save_image_bytes(
            base64.b64decode(raw_b64),
            purpose=purpose,
            mime=mime,
        )
    except Exception:
        path = ""

    return {
        "ok": True,
        "provider": provider,
        "mime": mime,
        "image_base64": raw_b64,
        "data_url": f"data:{mime};base64,{raw_b64}",
        "path": path,
        "seed": int(seed),
        "width": width,
        "height": height,
        "prompt": prompt,
        "negative_prompt": negative,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    import struct
    import zlib

    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _generate_demo_image(
    *,
    width: int,
    height: int,
    prompt: str,
    purpose: str,
    seed: int,
) -> dict[str, Any]:
    """
    Built-in test generator: solid-color PNG with a simple pattern.
    No Forge/Comfy required — used to verify face/fullbody UI + persist path.
    """
    import struct
    import zlib

    width = max(32, min(1024, int(width or 512)))
    height = max(32, min(1536, int(height or 512)))
    # Deterministic palette from seed + purpose
    purpose_l = (purpose or "").lower()
    if "full" in purpose_l or "body" in purpose_l:
        r, g, b = (40 + seed % 80, 70 + (seed // 3) % 100, 120 + (seed // 7) % 100)
    else:
        r, g, b = (120 + seed % 80, 90 + (seed // 5) % 90, 70 + (seed // 11) % 80)

    rows = []
    for y in range(height):
        row = bytearray([0])  # filter none
        for x in range(width):
            # Soft center shape only — no baked edge/frame (map UI draws rings).
            cx, cy = width / 2, height / (2.4 if "full" in purpose_l or "body" in purpose_l else 2.1)
            dx = (x - cx) / (width * 0.35)
            dy = (y - cy) / (height * (0.55 if "full" in purpose_l or "body" in purpose_l else 0.32))
            inside = dx * dx + dy * dy <= 1.0
            if inside:
                pr = min(255, r + int(30 * (1 - abs(dx))))
                pg = min(255, g + int(20 * (1 - abs(dy))))
                pb = min(255, b + 10)
            else:
                pr = max(0, r // 3)
                pg = max(0, g // 3)
                pb = max(0, b // 3 + 20)
            # stripe so face vs body are obvious
            if y % 48 < 2:
                pr = min(255, pr + 40)
            row.extend((pr, pg, pb))
        rows.append(bytes(row))
    raw = b"".join(rows)
    compressed = zlib.compress(raw, 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )
    return {
        "image_base64": base64.b64encode(png).decode("ascii"),
        "mime": "image/png",
        "demo": True,
        "note": f"demo:{purpose}:{prompt[:40]}",
    }


def _save_image_bytes(data: bytes, *, purpose: str, mime: str) -> str:
    PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".png" if "png" in mime else ".jpg"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in purpose)[:40] or "img"
    name = f"{safe}-{int(time.time())}-{uuid.uuid4().hex[:8]}{ext}"
    path = PORTRAIT_DIR / name
    path.write_bytes(data)
    # Relative path for UI / API consumers
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _face_lock_model_dirs(forge_root: str) -> list[Path]:
    """Folders under a configured Forge root that may hold face-lock weights."""
    if not str(forge_root or "").strip():
        return []
    layout = _forge_layout(str(forge_root).strip())
    bases = [layout["base"], layout["webui"], layout["models"].parent if layout.get("models") else layout["base"]]
    rels = (
        "models/ControlNet",
        "models/controlnet",
        "models/ipadapter",
        "models/IP-Adapter",
        "models/ip_adapter",
        "models/IpAdapter",
        "extensions/sd-webui-controlnet/models",
        "models/ControlNet/ipadapter",
    )
    out: list[Path] = []
    seen: set[str] = set()
    for base in bases:
        if not base:
            continue
        for rel in rels:
            p = Path(base) / rel.replace("/", os.sep)
            try:
                key = str(p.resolve()).lower() if p.exists() else str(p).lower()
            except Exception:
                key = str(p).lower()
            if key in seen:
                continue
            seen.add(key)
            if p.is_dir():
                out.append(p)
    return out


def scan_face_lock_files(forge_root: str | None = None) -> dict[str, Any]:
    """
    Walk the configured Forge install for InstantID / FaceID weight files.
    Paths are discovered relative to forge_root only (no machine-specific hardcodes).
    """
    cfg = get_image_config()
    root = str(forge_root if forge_root is not None else cfg.get("forge_root") or "").strip()
    result: dict[str, Any] = {
        "forge_root": root,
        "scanned_dirs": [],
        "instantid_files": [],
        "faceid_files": [],
        "other_face_files": [],
        "instantid_on_disk": False,
        "faceid_on_disk": False,
    }
    if not root or not Path(root).is_dir():
        return result
    exts = {".safetensors", ".bin", ".pt", ".pth", ".ckpt"}
    for folder in _face_lock_model_dirs(root):
        result["scanned_dirs"].append(str(folder))
        try:
            # One level deep is enough; avoid full-tree crawls of huge model packs
            entries = list(folder.iterdir())
        except OSError:
            continue
        for path in entries:
            try:
                if path.is_dir():
                    for child in path.iterdir():
                        if child.is_file() and child.suffix.lower() in exts:
                            _classify_face_lock_file(child, result)
                elif path.is_file() and path.suffix.lower() in exts:
                    _classify_face_lock_file(path, result)
            except OSError:
                continue
    result["instantid_on_disk"] = bool(result["instantid_files"])
    result["faceid_on_disk"] = bool(result["faceid_files"])
    return result


def _classify_face_lock_file(path: Path, result: dict[str, Any]) -> None:
    name = path.name
    nl = name.lower().replace(" ", "").replace("_", "").replace("-", "")
    entry = {"name": name, "path": str(path), "bytes": path.stat().st_size if path.is_file() else 0}
    if "instantid" in nl or ("instant" in nl and "id" in nl and "control" in nl) or (
        "instant" in nl and "ipadapter" in nl
    ):
        result["instantid_files"].append(entry)
        return
    if "ipadapterinstant" in nl or "adapterinstantid" in nl:
        result["instantid_files"].append(entry)
        return
    if "faceid" in nl or ("ipadapter" in nl and "face" in nl) or ("ip-adapter" in name.lower() and "face" in name.lower()):
        result["faceid_files"].append(entry)
        return
    if "face" in nl and ("ipadapter" in nl or "ipadapter" in path.parent.name.lower().replace("-", "").replace("_", "")):
        result["other_face_files"].append(entry)


def probe_character_lock(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Detect Forge-side tools for continuous characters (InstantID / IP-Adapter Face / ReActor).
    Combines live API lists with a scan of the configured forge_root on disk.
    """
    cfg = get_image_config() if config is None else dict(config)
    provider = _normalize_provider(cfg.get("provider"))
    forge_root = str(cfg.get("forge_root") or "").strip()
    disk = scan_face_lock_files(forge_root)
    out: dict[str, Any] = {
        "ok": False,
        "provider": provider,
        "api_ok": False,
        "controlnet": False,
        "reactor": False,
        "instantid_module": False,
        "ipadapter_face_module": False,
        "instantid_model": False,
        "ipadapter_face_model": False,
        "instantid_on_disk": bool(disk.get("instantid_on_disk")),
        "faceid_on_disk": bool(disk.get("faceid_on_disk")),
        "disk_scan": {
            "forge_root": disk.get("forge_root") or "",
            "scanned_dirs": list(disk.get("scanned_dirs") or [])[:12],
            "instantid_files": [f.get("name") for f in (disk.get("instantid_files") or [])[:12]],
            "faceid_files": [f.get("name") for f in (disk.get("faceid_files") or [])[:12]],
        },
        "modules": [],
        "models": [],
        "scripts_txt2img": [],
        "scripts_img2img": [],
        "recommended_mode": "light",
        "strong_ready": False,
        "message": "",
        "install_hints": [],
    }
    if provider not in {"forge"}:
        out["message"] = "Character lock strong mode is for Forge/A1111. Use light img2img ref or switch provider to Forge."
        return out

    # Disk flags are for install UI only — never invent ControlNet model names from them.
    out["instantid_on_disk"] = bool(disk.get("instantid_on_disk"))
    out["faceid_on_disk"] = bool(disk.get("faceid_on_disk"))
    if disk.get("instantid_on_disk"):
        out["instantid_model"] = True  # files present (may not be API-registered)

    found = discover_backend_base_url("forge", cfg, persist=True)
    if not found.get("ok"):
        out["ok"] = True
        out["api_ok"] = False
        out["strong_ready"] = False
        out["recommended_mode"] = "light"
        if disk.get("faceid_on_disk") or disk.get("instantid_on_disk"):
            out["message"] = (
                "Forge API offline. Face-lock weights were found under your Forge root on disk. "
                "Start Forge with --api for live ControlNet registration; until then Mørkyn uses light img2img when a face ref exists."
            )
        else:
            out["message"] = found.get("message") or (
                "Forge API offline — start Forge with --api. "
                "Set Forge install root so Mørkyn can scan for face-lock weights."
            )
            if not forge_root:
                out["install_hints"].append(
                    {
                        "title": "Set Forge install root",
                        "detail": "LLM Settings → Images → Browse… to your Forge/ForgeSD folder so Installs and face-lock scan can find models.",
                    }
                )
        out["install_hints"].extend(_face_lock_install_hints(out, forge_root))
        return out

    base = str(found.get("base_url") or cfg.get("forge_base_url") or DEFAULT_FORGE_URL).rstrip("/")
    out["api_ok"] = True
    out["base_url"] = base
    try:
        scripts = _http_json("GET", f"{base}/sdapi/v1/scripts", timeout=10)
        if isinstance(scripts, dict):
            out["scripts_txt2img"] = list(scripts.get("txt2img") or [])
            out["scripts_img2img"] = list(scripts.get("img2img") or [])
    except Exception as exc:
        out["message"] = f"Could not list scripts: {exc}"
        out["ok"] = True
        out["install_hints"] = _face_lock_install_hints(out, forge_root)
        return out
    all_scripts = [str(s).lower() for s in (out["scripts_txt2img"] + out["scripts_img2img"])]
    out["controlnet"] = any("controlnet" in s for s in all_scripts)
    out["reactor"] = any("reactor" in s or "roop" in s for s in all_scripts)
    try:
        mods_payload = _http_json("GET", f"{base}/controlnet/module_list", timeout=10)
        mods = mods_payload.get("module_list") if isinstance(mods_payload, dict) else mods_payload
        if isinstance(mods, list):
            out["modules"] = [str(m) for m in mods]
            if out["modules"]:
                out["controlnet"] = True
    except Exception:
        out["modules"] = []
    try:
        models_payload = _http_json("GET", f"{base}/controlnet/model_list", timeout=10)
        models = models_payload.get("model_list") if isinstance(models_payload, dict) else models_payload
        if isinstance(models, list):
            # ONLY API-registered ControlNet models — disk .bin names must never be injected.
            out["models"] = [str(m) for m in models if str(m) and str(m) != "None"]
            if out["models"]:
                out["controlnet"] = True
    except Exception:
        out["models"] = []

    for m in out["modules"]:
        ml = m.lower()
        ml_c = ml.replace("-", "").replace("_", "").replace(" ", "")
        if "instantid" in ml_c or ("instant" in ml and "id" in ml):
            out["instantid_module"] = True
        if "ipadapter" in ml_c and ("face" in ml_c or "insightface" in ml_c or "faceid" in ml_c):
            out["ipadapter_face_module"] = True
        if "faceid" in ml_c:
            out["ipadapter_face_module"] = True
        if "ip-adapter" in ml and "face" in ml:
            out["ipadapter_face_module"] = True
    # API-registered ControlNet models only
    out["ipadapter_face_model"] = False
    api_instant = False
    for m in out["models"]:
        ml = m.lower()
        ml_c = ml.replace("_", "").replace("-", "").replace(" ", "")
        if "instantid" in ml_c or ("instant" in ml and "id" in ml):
            api_instant = True
            out["instantid_model"] = True
        # FaceID .bin files in models/ipadapter are NOT ControlNet models.
        # Only treat as strong CN model if Forge registered it under ControlNet.
        if "faceid" in ml_c or ("ipadapter" in ml_c and "face" in ml_c and "instant" not in ml_c):
            out["ipadapter_face_model"] = True
        if "ip-adapter" in ml and "face" in ml and "instant" not in ml:
            out["ipadapter_face_model"] = True

    # Unit picker needs exact API names; store aliases for diagnostics only
    out["api_controlnet_models"] = list(out["models"][:40])
    out["api_face_lock_models"] = [
        m
        for m in out["models"]
        if _is_api_face_lock_model_name(m)
    ]

    # InstantID models/modules may be registered, but Forge API InstantID ControlNet
    # still crashes on this path (e.g. assert y.shape — y is None). Detect for UI only.
    instant_stack = _resolve_instantid_stack(out["modules"], out["models"])
    out["instantid_stack"] = {
        "ready": bool(instant_stack),
        "api_usable": False,  # do not send InstantID units via alwayson_scripts
        "insight_module": (instant_stack or {}).get("insight_module"),
        "keypoint_module": (instant_stack or {}).get("keypoint_module"),
        "ip_model": (instant_stack or {}).get("ip_model"),
        "control_model": (instant_stack or {}).get("control_model"),
    }
    out["instantid_api_supported"] = False

    api_safe_face = bool(out["api_face_lock_models"])
    if out["api_face_lock_models"]:
        out["ipadapter_face_model"] = True
        out["ipadapter_face_module"] = True

    # Strong API lock only for non-InstantID ControlNet face models or ReActor.
    # InstantID dual units crash Forge API (NoneType y.shape) — use light img2img instead.
    strong = bool(out["controlnet"] and (out["reactor"] or api_safe_face))
    out["strong_ready"] = strong
    out["api_safe_face_lock"] = api_safe_face
    out["ok"] = True
    out["install_hints"] = _face_lock_install_hints(out, forge_root)

    if strong:
        out["recommended_mode"] = "strong"
        bits = []
        if api_safe_face:
            bits.append("ControlNet face: " + out["api_face_lock_models"][0])
        if out["reactor"]:
            bits.append("ReActor")
        out["message"] = "Strong lock ready: " + ", ".join(bits) + "."
    else:
        out["recommended_mode"] = "light"
        # One short line — InstantID/FaceID details live in install_hints, not triple-repeated.
        if not forge_root:
            out["message"] = (
                "Light lock (img2img) ready when Forge is up. Set Forge root (Images → Browse…) for weight scans."
            )
        elif instant_stack:
            out["message"] = (
                "Light lock (img2img) — recommended. InstantID is on this Forge but not used over the API."
            )
        else:
            out["message"] = "Light lock (img2img) — recommended for face continuity."
    return out


def _is_api_face_lock_model_name(name: str) -> bool:
    """Non-InstantID ControlNet models that might lock face identity."""
    ml = str(name or "").lower()
    ml_c = ml.replace("_", "").replace("-", "").replace(" ", "")
    if "instant" in ml and "id" in ml:
        return False
    if "faceid" in ml_c:
        return True
    if "ipadapter" in ml_c and "face" in ml_c:
        return True
    if "ip-adapter" in ml and "face" in ml:
        return True
    return False


def _resolve_instantid_stack(modules: list[str], models: list[str]) -> dict[str, str] | None:
    """
    InstantID on Forge ControlNet needs two units with exact API names:
      1) InsightFace (InstantID) + ip-adapter_instant_id_sd15 […]
      2) instant_id_face_keypoints + control_instant_id_sd15 […]
    """
    insight = ""
    keypoints = ""
    for m in modules:
        ml = m.lower().replace(" ", "")
        if "insightface" in ml and "instant" in ml:
            insight = m
        if "instant_id_face_keypoints" in ml or (
            "instant" in ml and "keypoint" in ml
        ):
            keypoints = m
    ip_model = ""
    control_model = ""
    for m in models:
        ml = m.lower()
        if "ip-adapter" in ml and "instant" in ml:
            ip_model = m
        if "control" in ml and "instant" in ml:
            control_model = m
    if insight and keypoints and ip_model and control_model:
        return {
            "insight_module": insight,
            "keypoint_module": keypoints,
            "ip_model": ip_model,
            "control_model": control_model,
        }
    return None


def _face_lock_install_hints(probe: dict[str, Any], forge_root: str) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    if not forge_root:
        hints.append(
            {
                "title": "Forge install root",
                "detail": "Images → Browse… to your Forge folder so scans/installs work.",
            }
        )
    # Optional single note — not duplicated into the main status line.
    if probe.get("instantid_stack", {}).get("ready") and not probe.get("strong_ready"):
        hints.append(
            {
                "title": "InstantID",
                "detail": "Detected for Forge UI use only (API InstantID crashes on this build).",
            }
        )
    return hints


def _cn_unit(
    *,
    module: str,
    model: str,
    image_b64: str,
    weight: float,
) -> dict[str, Any]:
    """One Forge ControlNet unit with exact API module/model strings."""
    return {
        "enabled": True,
        "module": module,
        "model": model,
        "weight": float(max(0.1, min(1.5, weight))),
        "image": image_b64,
        "resize_mode": 1,
        "lowvram": False,
        "processor_res": 640,
        "threshold_a": 0.5,
        "threshold_b": 0.5,
        "guidance_start": 0.0,
        "guidance_end": 1.0,
        "pixel_perfect": True,
        "control_mode": 0,
    }


def _pick_face_lock_units(probe: dict[str, Any], weight: float, image_b64: str) -> list[dict[str, Any]]:
    """
    Build ControlNet units only for non-InstantID face models registered in the API.

    InstantID dual units are intentionally NOT sent: Forge API path crashes with
    AttributeError: 'NoneType' object has no attribute 'shape' (control y is None).
    FaceID .bin disk names are never used (KeyError if not in controlnet_filename_dict).
    Empty list → light img2img.
    """
    pure_b64 = _data_url_to_b64(image_b64)
    if not pure_b64:
        return []

    # InstantID stack may be "ready" for detection, but not usable over API.
    # Skip InstantID units entirely.

    models = [str(m) for m in (probe.get("api_face_lock_models") or [])]
    if not models:
        models = [str(m) for m in (probe.get("models") or []) if _is_api_face_lock_model_name(m)]
    if not models:
        return []
    modules = [str(m) for m in (probe.get("modules") or [])]
    module = ""
    for m in modules:
        ml = m.lower().replace("-", "").replace("_", "").replace(" ", "")
        if "instant" in ml:
            continue
        if "ipadapter" in ml and "face" in ml:
            module = m
            break
        if "faceid" in ml:
            module = m
            break
    if not module:
        for m in modules:
            if str(m).lower() == "none":
                module = m
                break
    if not module:
        return []
    return [_cn_unit(module=module, model=models[0], image_b64=pure_b64, weight=weight)]


def _pick_face_lock_unit(probe: dict[str, Any], weight: float, image_b64: str) -> dict[str, Any] | None:
    """Back-compat: first unit only."""
    units = _pick_face_lock_units(probe, weight, image_b64)
    return units[0] if units else None


def _controlnet_alwayson_args(
    unit: dict[str, Any] | list[dict[str, Any]] | None,
    unit_count: int = 1,
) -> dict[str, Any] | None:
    """ControlNet alwayson_scripts payload (one or more enabled units)."""
    if not unit:
        return None
    units = unit if isinstance(unit, list) else [unit]
    units = [u for u in units if isinstance(u, dict)]
    if not units:
        return None
    return {"ControlNet": {"args": units}}


def _face_identity_tags_from_prompt(prompt: str, *, limit: int = 14) -> str:
    """
    Pull face/identity-relevant tags for ADetailer's face inpaint prompt.
    Drops full-body framing / pose so the face pass focuses on likeness.
    """
    skip_sub = (
        "full body",
        "full-body",
        "standing",
        "from head to toe",
        "wide shot",
        "cowboy shot",
        "feet",
        "legs",
        "hands",
        "arms",
        "torso",
        "walking",
        "running",
        "sitting",
        "kneeling",
        "dynamic pose",
        "action pose",
        "legs out of frame",
    )
    prefer_sub = (
        "girl",
        "boy",
        "woman",
        "man",
        "person",
        "face",
        "portrait",
        "hair",
        "eye",
        "eyes",
        "bangs",
        "fringe",
        "skin",
        "expression",
        "smile",
        "looking",
        "viewer",
        "head",
        "nose",
        "mouth",
        "lip",
        "cheek",
        "jaw",
        "ear",
        "freckle",
        "scar",
        "makeup",
        "age",
        "young",
        "old",
        "beautiful",
        "handsome",
        "detailed face",
        "face focus",
    )
    face_tags: list[str] = []
    short_tags: list[str] = []
    for raw in str(prompt or "").split(","):
        t = raw.strip()
        if not t:
            continue
        low = t.lower()
        if any(s in low for s in skip_sub):
            continue
        words = low.replace("(", " ").replace(")", " ").replace(":", " ").split()
        if any(p in low for p in prefer_sub):
            face_tags.append(t)
        elif len(words) <= 3 and not any(
            sc in low for sc in ("city", "street", "forest", "room", "background", "sky", "neon")
        ):
            short_tags.append(t)
        if len(face_tags) >= limit:
            break
    tags = face_tags + [t for t in short_tags if t not in face_tags]
    if not tags:
        return ""
    # Always bias the AD face pass toward a clear face
    head = ["detailed face", "looking at viewer"]
    merged: list[str] = []
    seen: set[str] = set()
    for t in head + tags:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(t)
    return ", ".join(merged[: limit + 2])


def _adetailer_alwayson_args(
    cfg: dict[str, Any],
    *,
    purpose: str = "",
    prompt: str = "",
    negative: str = "",
    face_ref_b64: str | None = None,
) -> dict[str, Any] | None:
    """
    ADetailer alwayson_scripts block (Bing-su adetailer / Forge).

    Note: stock ADetailer has no API field for an external reference face image.
    When face_ref_b64 is provided and adetailer_use_face_ref is on, we:
      - use a face-focused ad_prompt (identity tags from the main prompt)
      - keep denoise moderate so the already face-locked pixels are refined, not replaced
      - rely on the main gen's face lock (img2img / CN) for actual likeness
    """
    if not bool(cfg.get("adetailer_enable")):
        return None
    purpose_l = str(purpose or "").lower()
    is_face = "face" in purpose_l or "portrait" in purpose_l
    is_body = "fullbody" in purpose_l or "body" in purpose_l or "full" in purpose_l
    if is_face and not bool(cfg.get("adetailer_on_face", True)):
        return None
    if is_body and not bool(cfg.get("adetailer_on_fullbody", True)):
        return None
    # Generic gens: allow if either on_face/on_fullbody is true
    if not is_face and not is_body:
        if not (bool(cfg.get("adetailer_on_face", True)) or bool(cfg.get("adetailer_on_fullbody", True))):
            return None
    model = str(cfg.get("adetailer_model") or "face_yolov8n.pt").strip() or "face_yolov8n.pt"
    try:
        denoise = float(cfg.get("adetailer_denoise") or 0.4)
    except (TypeError, ValueError):
        denoise = 0.4
    denoise = max(0.1, min(0.9, denoise))

    use_face_ref = bool(cfg.get("adetailer_use_face_ref", True)) and bool(face_ref_b64)
    ad_prompt = ""
    ad_negative = ""
    if use_face_ref:
        # Identity-preserving face inpaint: detail the locked face, don't invent a new one.
        ad_prompt = _face_identity_tags_from_prompt(prompt)
        ad_negative = str(negative or "").strip()[:800]
        # Slightly gentler denoise when we have a real face to keep
        if is_body or is_face:
            denoise = min(denoise, max(0.25, denoise * 0.9))
            denoise = round(max(0.2, min(0.55, denoise)), 3)

    tab = {
        "ad_model": model,
        "ad_model_classes": "",
        "ad_tab_enable": True,
        # Empty ad_prompt = reuse main prompt. With face ref we send face-focused tags.
        "ad_prompt": ad_prompt,
        "ad_negative_prompt": ad_negative,
        "ad_confidence": 0.3 if not use_face_ref else 0.28,
        "ad_mask_k": 0,
        "ad_mask_min_ratio": 0.0,
        "ad_mask_max_ratio": 1.0,
        "ad_dilate_erode": 4,
        "ad_mask_blur": 4 if not use_face_ref else 6,
        "ad_denoising_strength": denoise,
        "ad_inpaint_only_masked": True,
        "ad_inpaint_only_masked_padding": 32 if not use_face_ref else 40,
        "ad_use_steps": False,
        "ad_use_cfg_scale": False,
        "ad_restore_face": False,
        # No external image field exists; CN inpaint (if user has model) only structures the crop.
        "ad_controlnet_model": "None",
        "ad_controlnet_module": "None",
        "ad_controlnet_weight": 1.0,
    }
    # Official wiki: [enable, skip_img2img, {settings...}]
    return {
        "ADetailer": {
            "args": [True, False, tab],
        }
    }


def _merge_alwayson_scripts(*parts: dict[str, Any] | None) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    for part in parts:
        if isinstance(part, dict) and part:
            merged.update(part)
    return merged or None


def resolve_character_consistency_mode(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = get_image_config() if cfg is None else dict(cfg)
    raw = str(cfg.get("character_consistency") or "auto").strip().lower()
    probe = probe_character_lock(cfg)
    if raw == "off":
        return {"mode": "off", "probe": probe, "use_light_img2img": False, "use_strong": False}
    if raw == "light":
        return {"mode": "light", "probe": probe, "use_light_img2img": True, "use_strong": False}
    if raw == "strong":
        return {
            "mode": "strong" if probe.get("strong_ready") else "light",
            "probe": probe,
            "use_light_img2img": not probe.get("strong_ready"),
            "use_strong": bool(probe.get("strong_ready")),
            "fallback_reason": None if probe.get("strong_ready") else probe.get("message"),
        }
    # auto
    if probe.get("strong_ready"):
        return {"mode": "strong", "probe": probe, "use_light_img2img": False, "use_strong": True}
    return {"mode": "light", "probe": probe, "use_light_img2img": True, "use_strong": False}


def _generate_forge(
    *,
    base_url: str,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg_scale: float,
    seed: int,
    timeout: int,
    sampler_name: str | None = None,
    scheduler: str | None = None,
    checkpoint: str | None = None,
    vae: str | None = None,
    clip_skip: int = 1,
    restore_faces: bool = False,
    tiling: bool = False,
    enable_hr: bool = False,
    hr_scale: float = 1.5,
    hr_upscaler: str = "Latent",
    denoising_strength: float = 0.45,
    init_images: list[str] | None = None,
    alwayson_scripts: dict[str, Any] | None = None,
    prefer_txt2img_with_controlnet: bool = False,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    sampler = (sampler_name or "").strip() or "Euler a"
    use_img2img = bool(init_images and init_images[0]) and not prefer_txt2img_with_controlnet
    body: dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": cfg_scale,
        "seed": seed,
        "batch_size": 1,
        "n_iter": 1,
        "sampler_name": sampler,
        "restore_faces": bool(restore_faces),
        "tiling": bool(tiling),
        "enable_hr": bool(enable_hr) and not use_img2img,
    }
    sched = (scheduler or "").strip()
    if sched and sched.lower() not in {"", "automatic", "auto"}:
        body["scheduler"] = sched
    if enable_hr and not use_img2img:
        body["hr_scale"] = float(hr_scale or 1.5)
        body["hr_upscaler"] = str(hr_upscaler or "Latent")
        body["denoising_strength"] = float(denoising_strength or 0.45)
    if use_img2img:
        body["init_images"] = [str(init_images[0])]
        body["denoising_strength"] = float(denoising_strength if denoising_strength is not None else 0.65)
        body["resize_mode"] = 0  # just resize
    override: dict[str, Any] = {}
    if checkpoint and str(checkpoint).strip():
        override["sd_model_checkpoint"] = str(checkpoint).strip()
    if vae and str(vae).strip() and str(vae).strip().lower() not in {"automatic", "auto", "none"}:
        override["sd_vae"] = str(vae).strip()
    if int(clip_skip or 1) > 1:
        override["CLIP_stop_at_last_layers"] = int(clip_skip)
    if override:
        body["override_settings"] = override
        body["override_settings_restore_afterwards"] = True
    if alwayson_scripts:
        body["alwayson_scripts"] = alwayson_scripts
    endpoint = f"{base}/sdapi/v1/img2img" if use_img2img else f"{base}/sdapi/v1/txt2img"
    payload = _http_json("POST", endpoint, body=body, timeout=timeout)
    images = payload.get("images") if isinstance(payload, dict) else None
    if not images:
        raise RuntimeError("Forge/A1111 returned no images. Is --api enabled?")
    # A1111 sometimes appends metadata after a comma in the base64 field.
    raw = str(images[0]).split(",", 1)[0]
    return {
        "image_base64": raw,
        "mime": "image/png",
        "raw": payload,
        "mode": "img2img" if use_img2img else "txt2img",
        "used_controlnet": bool(alwayson_scripts),
    }


def _load_comfy_workflow(workflow_name: str) -> dict[str, Any]:
    name = (workflow_name or "txt2img_api.json").strip()
    # Prevent path escape
    name = Path(name).name
    path = WORKFLOW_DIR / name
    if not path.is_file():
        path = WORKFLOW_DIR / "txt2img_api.json"
    if not path.is_file():
        raise RuntimeError(f"ComfyUI workflow missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("ComfyUI workflow must be a JSON object (API format).")
    return data


def _inject_comfy_workflow(
    workflow: dict[str, Any],
    *,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg_scale: float,
    seed: int,
    checkpoint: str,
    sampler_name: str = "euler",
    scheduler: str = "normal",
) -> dict[str, Any]:
    """
    Best-effort injection for API-format graphs.
    Recognizes CheckpointLoaderSimple, CLIPTextEncode, EmptyLatentImage, KSampler(+Advanced).
    """
    graph = copy.deepcopy(workflow)
    positive_set = False
    negative_set = False
    for _node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.setdefault("inputs", {})
        if not isinstance(inputs, dict):
            continue
        if class_type == "CheckpointLoaderSimple" and checkpoint:
            inputs["ckpt_name"] = checkpoint
        elif class_type == "EmptyLatentImage":
            inputs["width"] = width
            inputs["height"] = height
            inputs["batch_size"] = int(inputs.get("batch_size") or 1)
        elif class_type in {"KSampler", "KSamplerAdvanced"}:
            if "seed" in inputs or class_type == "KSampler":
                inputs["seed"] = seed
            if "noise_seed" in inputs:
                inputs["noise_seed"] = seed
            if "steps" in inputs:
                inputs["steps"] = steps
            if "cfg" in inputs:
                inputs["cfg"] = cfg_scale
            if sampler_name and "sampler_name" in inputs:
                inputs["sampler_name"] = sampler_name
            if scheduler and "scheduler" in inputs:
                inputs["scheduler"] = scheduler
        elif class_type == "CLIPTextEncode":
            # First CLIPTextEncode -> positive, second -> negative (common export order).
            if not positive_set:
                inputs["text"] = prompt
                positive_set = True
            elif not negative_set:
                inputs["text"] = negative_prompt
                negative_set = True
    # Placeholder string replace for hand-authored templates
    blob = json.dumps(graph)
    blob = (
        blob.replace("{{PROMPT}}", json.dumps(prompt)[1:-1])
        .replace("{{NEGATIVE}}", json.dumps(negative_prompt)[1:-1])
        .replace("{{WIDTH}}", str(width))
        .replace("{{HEIGHT}}", str(height))
        .replace("{{STEPS}}", str(steps))
        .replace("{{CFG}}", str(cfg_scale))
        .replace("{{SEED}}", str(seed))
        .replace("{{CHECKPOINT}}", json.dumps(checkpoint)[1:-1] if checkpoint else "")
        .replace("{{SAMPLER}}", json.dumps(sampler_name)[1:-1] if sampler_name else "euler")
        .replace("{{SCHEDULER}}", json.dumps(scheduler)[1:-1] if scheduler else "normal")
    )
    return json.loads(blob)


def _generate_comfy(
    *,
    base_url: str,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg_scale: float,
    seed: int,
    checkpoint: str,
    workflow_name: str,
    timeout: int,
    sampler_name: str = "euler",
    scheduler: str = "normal",
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    workflow = _load_comfy_workflow(workflow_name)
    graph = _inject_comfy_workflow(
        workflow,
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        cfg_scale=cfg_scale,
        seed=seed,
        checkpoint=checkpoint,
        sampler_name=sampler_name or "euler",
        scheduler=scheduler or "normal",
    )
    client_id = uuid.uuid4().hex
    queued = _http_json(
        "POST",
        f"{base}/prompt",
        body={"prompt": graph, "client_id": client_id},
        timeout=min(60, timeout),
    )
    prompt_id = str(queued.get("prompt_id") or "")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return prompt_id: {queued}")

    # Poll history until outputs appear.
    deadline = time.time() + timeout
    outputs: dict[str, Any] = {}
    while time.time() < deadline:
        hist = _http_json("GET", f"{base}/history/{prompt_id}", timeout=15)
        entry = hist.get(prompt_id) if isinstance(hist, dict) else None
        if isinstance(entry, dict):
            status = entry.get("status") or {}
            if isinstance(status, dict) and status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI job error: {status}")
            outs = entry.get("outputs") or {}
            if outs:
                outputs = outs
                break
        time.sleep(0.75)
    if not outputs:
        raise RuntimeError("ComfyUI timed out waiting for image output.")

    # Find first image in outputs
    file_info = None
    for _nid, node_out in outputs.items():
        if not isinstance(node_out, dict):
            continue
        images = node_out.get("images") or []
        if images:
            file_info = images[0]
            break
    if not file_info:
        raise RuntimeError("ComfyUI finished but produced no images.")

    filename = str(file_info.get("filename") or "")
    subfolder = str(file_info.get("subfolder") or "")
    img_type = str(file_info.get("type") or "output")
    if not filename:
        raise RuntimeError("ComfyUI image filename missing.")
    from urllib.parse import urlencode

    qs = urlencode({"filename": filename, "subfolder": subfolder, "type": img_type})
    img_bytes = _http_bytes(f"{base}/view?{qs}", timeout=min(60, timeout))
    return {
        "image_base64": base64.b64encode(img_bytes).decode("ascii"),
        "mime": "image/png",
        "prompt_id": prompt_id,
    }


# ---------------------------------------------------------------------------
# Image presets (editable cfg file)
# ---------------------------------------------------------------------------


def default_image_presets() -> dict[str, Any]:
    if PRESETS_DEFAULT_PATH.is_file():
        try:
            data = json.loads(PRESETS_DEFAULT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {
        "version": 4,
        "shared": {
            "negative_prompt": (
                "(child:1.3), lowres, blurry, deformed, bad anatomy, extra limbs, extra fingers, "
                "watermark, text, logo, multiple people, "
                "side profile, facing away, looking away, from behind, "
                "frame, border, picture frame"
            ),
            "sampler_name": "Euler a",
            "scheduler": "Automatic",
            "timeout_seconds": 180,
            "share_seed_base": True,
        },
        "face": {
            "width": 512,
            "height": 512,
            "steps": 26,
            "cfg_scale": 7.5,
            "style": "",
            "extra_prompt": "",
            "negative_extra": "",
        },
        "fullbody": {
            "width": 576,
            "height": 768,
            "steps": 30,
            "cfg_scale": 8,
            "style": "",
            "extra_prompt": "",
            "negative_extra": "",
        },
        "launch": {
            "auto_launch_if_offline": True,
            "forge_root": "",
            "comfy_root": "",
            "forge_launch_rel": "webui-user.bat",
            "comfy_launch_rel": "main.py",
            "ready_timeout_seconds": 120,
        },
    }


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_image_presets() -> dict[str, Any]:
    base = default_image_presets()
    if PRESETS_USER_PATH.is_file():
        try:
            user = json.loads(PRESETS_USER_PATH.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                base = _deep_merge(base, user)
        except Exception:
            pass
    # Overlay roots from image_config when present
    try:
        cfg = get_image_config()
        launch = base.setdefault("launch", {})
        if isinstance(launch, dict):
            if cfg.get("forge_root"):
                launch["forge_root"] = str(cfg.get("forge_root") or "")
            if cfg.get("comfy_root"):
                launch["comfy_root"] = str(cfg.get("comfy_root") or "")
            if "auto_launch_if_offline" in cfg:
                launch["auto_launch_if_offline"] = bool(cfg.get("auto_launch_if_offline"))
    except Exception:
        pass
    return base


def save_image_presets(payload: dict[str, Any] | None) -> dict[str, Any]:
    current = load_image_presets()
    if isinstance(payload, dict):
        current = _deep_merge(current, payload)
    current["version"] = int(current.get("version") or 1)
    PRESETS_USER_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRESETS_USER_PATH.write_text(json.dumps(current, ensure_ascii=True, indent=2), encoding="utf-8")
    return current


def reset_image_presets() -> dict[str, Any]:
    defaults = default_image_presets()
    PRESETS_USER_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRESETS_USER_PATH.write_text(json.dumps(defaults, ensure_ascii=True, indent=2), encoding="utf-8")
    return defaults


def public_image_presets() -> dict[str, Any]:
    presets = load_image_presets()
    return {
        **presets,
        "user_path": str(PRESETS_USER_PATH.relative_to(ROOT)).replace("\\", "/")
        if PRESETS_USER_PATH.is_relative_to(ROOT)
        else str(PRESETS_USER_PATH),
        "default_path": str(PRESETS_DEFAULT_PATH.relative_to(ROOT)).replace("\\", "/")
        if PRESETS_DEFAULT_PATH.is_relative_to(ROOT)
        else str(PRESETS_DEFAULT_PATH),
    }


# ---------------------------------------------------------------------------
# Readiness, path search, launch
# ---------------------------------------------------------------------------


def _root_looks_like_forge(path: Path) -> bool:
    if not path.is_dir():
        return False
    for name in ("webui-user.bat", "webui.bat", "launch.py", "webui.py", "run_forge_api.bat"):
        if (path / name).is_file():
            return True
    # Portable pack root (ForgeSD): webui/ + system/python/
    if (path / "webui" / "webui-user.bat").is_file() or (path / "webui" / "modules_forge").is_dir():
        return True
    if (path / "modules_forge").is_dir():
        return True
    return False


def _root_looks_like_comfy(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / "main.py").is_file() and (
        (path / "comfy").is_dir() or (path / "nodes.py").is_file() or (path / "execution.py").is_file()
    ):
        return True
    # Portable layouts sometimes nest one level
    if (path / "ComfyUI" / "main.py").is_file():
        return True
    if (path / "comfyui" / "main.py").is_file():
        return True
    return False


def validate_backend_root(kind: str, root: str) -> dict[str, Any]:
    kind = str(kind or "").lower()
    path = Path(str(root or "").strip())
    if not str(root or "").strip():
        return {"ok": False, "kind": kind, "message": "Root path is empty."}
    if not path.is_dir():
        return {"ok": False, "kind": kind, "path": str(path), "message": "Path is not a directory."}
    if kind == "forge":
        ok = _root_looks_like_forge(path)
        return {
            "ok": ok,
            "kind": "forge",
            "path": str(path),
            "message": "Forge/A1111 root looks valid." if ok else "No webui-user.bat / webui.py found here.",
        }
    if kind == "comfyui":
        ok = _root_looks_like_comfy(path)
        resolved = path
        if not ok and (path / "ComfyUI").is_dir() and _root_looks_like_comfy(path / "ComfyUI"):
            ok = True
            resolved = path / "ComfyUI"
        return {
            "ok": ok,
            "kind": "comfyui",
            "path": str(resolved),
            "message": "ComfyUI root looks valid." if ok else "No ComfyUI main.py layout found here.",
        }
    return {"ok": False, "kind": kind, "message": "Unknown kind (use forge or comfyui)."}


def image_readiness(*, launch_if_offline: bool = False) -> dict[str, Any]:
    cfg = get_image_config()
    presets = load_image_presets()
    launch = presets.get("launch") if isinstance(presets.get("launch"), dict) else {}
    provider = _normalize_provider(cfg.get("provider"))
    missing: list[dict[str, Any]] = []
    install_hints = [
        {
            "label": "Forge install guide",
            "url": "https://github.com/lllyasviel/stable-diffusion-webui-forge",
        },
        {
            "label": "ComfyUI install guide",
            "url": "https://github.com/comfyanonymous/ComfyUI",
        },
        {
            "label": "Mørkyn image docs",
            "url": "/docs" if False else "docs/ConnectImages.md",
        },
    ]

    forge_root = str(cfg.get("forge_root") or launch.get("forge_root") or "").strip()
    comfy_root = str(cfg.get("comfy_root") or launch.get("comfy_root") or "").strip()
    forge_valid = validate_backend_root("forge", forge_root) if forge_root else {"ok": False}
    comfy_valid = validate_backend_root("comfyui", comfy_root) if comfy_root else {"ok": False}
    auto_launch = bool(cfg.get("auto_launch_if_offline") if "auto_launch_if_offline" in cfg else launch.get("auto_launch_if_offline", True))

    if provider == "off":
        missing.append(
            {
                "code": "provider_off",
                "title": "Image provider is Off",
                "action": "open_image_settings",
                "detail": "Set provider to Demo (test), Forge / A1111, or ComfyUI under Images settings.",
            }
        )
        return {
            "provider": "off",
            "api_ok": False,
            "api_message": "Provider off",
            "forge_root_set": bool(forge_root),
            "forge_root_valid": bool(forge_valid.get("ok")),
            "comfy_root_set": bool(comfy_root),
            "comfy_root_valid": bool(comfy_valid.get("ok")),
            "launch_available": False,
            "auto_launch_if_offline": auto_launch,
            "missing": missing,
            "install_hints": install_hints,
        }

    if provider == "demo":
        return {
            "provider": "demo",
            "api_ok": True,
            "api_message": "Demo generator ready (no external app).",
            "forge_root_set": bool(forge_root),
            "forge_root_valid": bool(forge_valid.get("ok")),
            "comfy_root_set": bool(comfy_root),
            "comfy_root_valid": bool(comfy_valid.get("ok")),
            "launch_available": False,
            "auto_launch_if_offline": auto_launch,
            "missing": [],
            "install_hints": install_hints,
        }

    probe = probe_image_backend(cfg)
    api_ok = bool(probe.get("ok"))
    launched = None
    # If the port is already occupied (Forge open / still loading), NEVER spawn another
    # instance — just wait for the API or report offline-but-occupied.
    if not api_ok and probe.get("port_open"):
        wait_s = int(launch.get("ready_timeout_seconds") or 90)
        deadline = time.time() + max(10, min(180, wait_s))
        while time.time() < deadline:
            probe = probe_image_backend(cfg)
            if probe.get("ok"):
                api_ok = True
                break
            if not probe.get("port_open"):
                break
            time.sleep(2.0)
    # Only spawn when truly nothing is listening AND caller + settings allow it.
    elif not api_ok and launch_if_offline and auto_launch:
        launched = launch_image_backend(provider, force=False)
        if launched.get("already_running") or launched.get("pending"):
            # Port/process already owned — poll, do not treat as failure yet.
            wait_s = int(launch.get("ready_timeout_seconds") or 120)
            deadline = time.time() + max(15, min(300, wait_s))
            while time.time() < deadline:
                probe = probe_image_backend(cfg)
                if probe.get("ok"):
                    api_ok = True
                    break
                time.sleep(2.0)
        elif launched.get("ok") and launched.get("launched"):
            wait_s = int(launch.get("ready_timeout_seconds") or 120)
            deadline = time.time() + max(15, min(300, wait_s))
            while time.time() < deadline:
                probe = probe_image_backend(cfg)
                if probe.get("ok"):
                    api_ok = True
                    break
                time.sleep(2.0)

    if not api_ok:
        detail = str(probe.get("message") or "Connection failed")
        if probe.get("port_open") or (launched and launched.get("pending")):
            missing.append(
                {
                    "code": "api_loading",
                    "title": f"{provider} is open but API not ready",
                    "action": "wait_or_enable_api",
                    "detail": detail
                    + " Mørkyn will not open another Forge window. Wait for the existing one, or enable --api.",
                }
            )
        else:
            missing.append(
                {
                    "code": "api_offline",
                    "title": f"{provider} API is not reachable",
                    "action": "launch_or_start",
                    "detail": detail,
                }
            )
        if provider == "forge" and not forge_root:
            missing.append(
                {
                    "code": "forge_root_missing",
                    "title": "Forge install root not set",
                    "action": "set_forge_root",
                    "detail": "Enter the Forge folder path or use Allow search, then Save.",
                }
            )
        if provider == "comfyui" and not comfy_root:
            missing.append(
                {
                    "code": "comfy_root_missing",
                    "title": "ComfyUI install root not set",
                    "action": "set_comfy_root",
                    "detail": "Enter the ComfyUI folder path or use Allow search, then Save.",
                }
            )

    return {
        "provider": provider,
        "api_ok": api_ok,
        "api_message": probe.get("message") or "",
        "forge_root_set": bool(forge_root),
        "forge_root_valid": bool(forge_valid.get("ok")),
        "comfy_root_set": bool(comfy_root),
        "comfy_root_valid": bool(comfy_valid.get("ok")),
        "launch_available": bool(
            (provider == "forge" and forge_valid.get("ok"))
            or (provider == "comfyui" and comfy_valid.get("ok"))
        ),
        "auto_launch_if_offline": auto_launch,
        "launched": launched,
        "missing": missing,
        "install_hints": install_hints,
        "last_launch": dict(_last_launch) if _last_launch else None,
    }


def search_backend_roots(kind: str, *, max_results: int = 12, max_seconds: float = 12.0) -> dict[str, Any]:
    """
    Bounded search for Forge or ComfyUI installs (user-consented).
    Scans a short list of roots with limited depth — not a full-disk crawl.
    """
    kind = str(kind or "").lower()
    if kind not in {"forge", "comfyui"}:
        return {"ok": False, "kind": kind, "candidates": [], "error": "kind must be forge or comfyui"}

    home = Path.home()
    seeds: list[Path] = [
        home,
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        Path("C:/") if os.name == "nt" else Path("/"),
        Path("D:/") if os.name == "nt" else Path.home(),
        Path("E:/") if os.name == "nt" else Path.home(),
        Path("D:/ForgeSD") if os.name == "nt" else Path.home(),
        ROOT.parent,
        ROOT,
    ]
    # Common names
    name_hints = (
        ("forge", ("stable-diffusion-webui-forge", "webui-forge", "sd-webui-forge", "stable-diffusion-webui", "forge", "forgesd"))
        if kind == "forge"
        else ("comfyui", ("ComfyUI", "comfyui", "ComfyUI_windows_portable"))
    )[1]

    skip_dir_names = {
        "windows",
        "program files",
        "program files (x86)",
        "programdata",
        "$recycle.bin",
        "system volume information",
        "node_modules",
        ".git",
        "appdata",
        "windowsapps",
    }
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    deadline = time.time() + max(3.0, min(30.0, max_seconds))

    def add_candidate(path: Path, score: int, reason: str) -> None:
        key = str(path.resolve()).lower() if path.exists() else str(path).lower()
        if key in seen:
            return
        seen.add(key)
        check = validate_backend_root(kind, str(path))
        if not check.get("ok"):
            return
        candidates.append(
            {
                "path": check.get("path") or str(path),
                "score": score,
                "reason": reason,
            }
        )

    for seed in seeds:
        if time.time() > deadline or len(candidates) >= max_results:
            break
        try:
            if not seed.exists():
                continue
        except Exception:
            continue
        # Direct children match by name
        try:
            if seed.is_dir():
                for child in seed.iterdir():
                    if time.time() > deadline or len(candidates) >= max_results:
                        break
                    try:
                        if not child.is_dir():
                            continue
                        lname = child.name.lower()
                        if lname in skip_dir_names:
                            continue
                        if any(h.lower() in lname for h in name_hints):
                            if kind == "forge" and _root_looks_like_forge(child):
                                add_candidate(child, 90, "name match under seed")
                            elif kind == "comfyui" and _root_looks_like_comfy(child):
                                add_candidate(child, 90, "name match under seed")
                            elif kind == "comfyui" and _root_looks_like_comfy(child / "ComfyUI"):
                                add_candidate(child / "ComfyUI", 95, "portable nested ComfyUI")
                    except Exception:
                        continue
                # One more level for Desktop/Documents/Downloads only
                if seed.name.lower() in {"desktop", "documents", "downloads"} or seed == home:
                    for child in list(seed.iterdir())[:80]:
                        if time.time() > deadline or len(candidates) >= max_results:
                            break
                        try:
                            if not child.is_dir() or child.name.lower() in skip_dir_names:
                                continue
                            for grand in list(child.iterdir())[:40]:
                                if time.time() > deadline or len(candidates) >= max_results:
                                    break
                                try:
                                    if not grand.is_dir():
                                        continue
                                    gl = grand.name.lower()
                                    if any(h.lower() in gl for h in name_hints):
                                        if kind == "forge" and _root_looks_like_forge(grand):
                                            add_candidate(grand, 70, "nested name match")
                                        elif kind == "comfyui" and _root_looks_like_comfy(grand):
                                            add_candidate(grand, 70, "nested name match")
                                except Exception:
                                    continue
                        except Exception:
                            continue
        except Exception:
            continue

    candidates.sort(key=lambda c: (-int(c.get("score") or 0), str(c.get("path") or "")))
    return {
        "ok": True,
        "kind": kind,
        "candidates": candidates[:max_results],
        "scanned_seconds": round(min(max_seconds, time.time() - (deadline - max_seconds)), 2),
        "message": (
            f"Found {min(len(candidates), max_results)} candidate(s)."
            if candidates
            else "No installs found in common locations. Enter the path manually."
        ),
    }


def launch_image_backend(provider: str | None = None, *, force: bool = False) -> dict[str, Any]:
    """
    Start Forge or ComfyUI from configured root (allowlisted launch scripts only).

    Always probes the API first. If already reachable, does **not** open another terminal.
    If the configured port is already open (UI loading / API not ready), also refuses.
    Within a long cooldown after a launch request, refuses to spawn duplicates.
    """
    global _last_launch, _last_launch_mono
    cfg = get_image_config()
    presets = load_image_presets()
    launch = presets.get("launch") if isinstance(presets.get("launch"), dict) else {}
    provider = _normalize_provider(provider or cfg.get("provider"))
    if provider == "off":
        return {
            "ok": False,
            "error": "Provider is off. Set provider to Forge or ComfyUI (or Demo to test without launching).",
        }
    if provider == "demo":
        return {
            "ok": True,
            "provider": "demo",
            "message": "Demo provider needs no launch.",
            "pid": None,
            "already_running": True,
        }

    # 1) Prefer an already-open backend — never open a second console.
    probe = probe_image_backend(cfg)
    if probe.get("ok") and not force:
        return {
            "ok": True,
            "provider": provider,
            "already_running": True,
            "launched": False,
            "message": (
                f"{provider} API already reachable"
                + (f" ({probe.get('message')})" if probe.get("message") else "")
                + ". Not starting another instance."
            ),
            "probe": probe,
        }

    # 1b) Port already taken (Forge/Comfy booting or WebUI without ready API).
    if probe.get("port_open") and not force:
        return {
            "ok": True,
            "provider": provider,
            "already_running": True,
            "launched": False,
            "pending": True,
            "message": (
                f"{provider} already has something on its port "
                f"({probe.get('base_url') or 'configured URL'}). "
                "Not opening another Forge/Comfy window. Wait for it to finish loading, "
                "or ensure it was started with --api. Use Test connection."
            ),
            "probe": probe,
        }

    # 1c) Cooldown after a recent launch (API may still be loading models).
    now = time.monotonic()
    if (
        not force
        and _last_launch
        and str(_last_launch.get("provider") or "") == provider
        and (now - _last_launch_mono) < _LAUNCH_COOLDOWN_S
    ):
        return {
            "ok": True,
            "provider": provider,
            "already_running": False,
            "launched": False,
            "pending": True,
            "message": (
                f"A {provider} launch was already requested "
                f"{int(now - _last_launch_mono)}s ago. Waiting for that API — not opening another terminal. "
                "Use Test connection; force-restart only if the previous window failed."
            ),
            "last_launch": dict(_last_launch),
            "probe": probe,
        }

    if provider == "forge":
        raw_root = str(cfg.get("forge_root") or launch.get("forge_root") or "").strip().strip('"').strip("'")
        pack_root = Path(raw_root)
        if not pack_root.is_dir():
            return {
                "ok": False,
                "error": f"Install root is not a directory: {pack_root}. Re-select with Allow search and Save.",
            }
        # Resolve pack vs webui folder without writing anything into the install.
        if (pack_root / "webui" / "webui.bat").is_file():
            pack_root = pack_root
            webui_dir = pack_root / "webui"
        elif (pack_root / "webui.bat").is_file():
            webui_dir = pack_root
            pack_root = pack_root.parent if (pack_root.parent / "environment.bat").is_file() else pack_root
        else:
            return {
                "ok": False,
                "error": f"Could not find webui.bat under {raw_root}.",
            }
        morkyn_launcher = ROOT / "tools" / "morkyn_forge_api.bat"
        if not morkyn_launcher.is_file():
            return {
                "ok": False,
                "error": f"Missing Morkyn launcher {morkyn_launcher}. Reinstall/update Morkyn tools.",
            }
        script = morkyn_launcher
        root = morkyn_launcher.parent
        launch_env = {
            **os.environ,
            "MORKYN_FORGE_ROOT": str(pack_root if (pack_root / "webui" / "webui.bat").is_file() else webui_dir),
            "MORKYN_FORGE_EXTRA_ARGS": str(
                cfg.get("forge_extra_args")
                or launch.get("forge_extra_args")
                or "--xformers --always-offload-from-vram"
            ),
        }
        # Prefer pack root when environment.bat lives there.
        if (Path(raw_root) / "environment.bat").is_file():
            launch_env["MORKYN_FORGE_ROOT"] = str(Path(raw_root))
        elif (pack_root / "environment.bat").is_file():
            launch_env["MORKYN_FORGE_ROOT"] = str(pack_root)
    elif provider == "comfyui":
        raw_root = str(cfg.get("comfy_root") or launch.get("comfy_root") or "").strip().strip('"').strip("'")
        pack_root = Path(raw_root)
        if not pack_root.is_dir():
            return {
                "ok": False,
                "error": f"Install root is not a directory: {pack_root}. Re-select with Allow search and Save.",
            }
        morkyn_launcher = ROOT / "tools" / "morkyn_comfy_api.bat"
        if not morkyn_launcher.is_file():
            return {
                "ok": False,
                "error": f"Missing Morkyn launcher {morkyn_launcher}.",
            }
        script = morkyn_launcher
        root = morkyn_launcher.parent
        launch_env = {
            **os.environ,
            "MORKYN_COMFY_ROOT": str(pack_root),
        }
    else:
        return {"ok": False, "error": f"Cannot launch provider: {provider}"}

    # 1d) A python process for this backend is already running (common while models load
    # and the port is not open yet). Do not start a second ForgeSD.
    if not force:
        proc_hint = _windows_backend_process_running(provider, raw_root)
        if proc_hint.get("running"):
            return {
                "ok": True,
                "provider": provider,
                "already_running": True,
                "launched": False,
                "pending": True,
                "message": (
                    f"Detected an existing {provider} process already running "
                    f"(models may still be loading). Not opening another terminal. "
                    f"Wait, then use Test connection."
                ),
                "process_hint": proc_hint.get("detail") or "",
                "probe": probe,
            }

    if not raw_root:
        return {
            "ok": False,
            "error": (
                f"No {provider} install root saved. Use Allow search or paste the folder path on the "
                f"{'Forge' if provider == 'forge' else 'ComfyUI'} tab, then Save image settings."
            ),
        }

    # Windows: PowerShell Start-Process on Morkyn's bat (install stays untouched).
    try:
        if os.name == "nt":

            def _ps_lit(value: str) -> str:
                return "'" + str(value).replace("'", "''") + "'"

            # Pass env vars into the child via PowerShell.
            env_assigns = []
            for key in ("MORKYN_FORGE_ROOT", "MORKYN_FORGE_EXTRA_ARGS", "MORKYN_COMFY_ROOT"):
                if key in launch_env and launch_env[key]:
                    env_assigns.append(f"$env:{key}={_ps_lit(str(launch_env[key]))};")
            env_prefix = " ".join(env_assigns)
            ps = (
                env_prefix
                + " Start-Process -FilePath "
                + _ps_lit(str(script))
                + " -WorkingDirectory "
                + _ps_lit(str(root))
                + " -WindowStyle Normal"
            )
            method = "morkyn_launcher_bat"
            create_no_window = 0x08000000
            proc = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps,
                ],
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=create_no_window,
                close_fds=True,
            )
            try:
                _out, err = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                return {
                    "ok": False,
                    "error": (
                        f"Timed out starting {script.name} via PowerShell. "
                        f"Run manually: set MORKYN_FORGE_ROOT=... && {script}"
                    ),
                }
            if proc.returncode not in (0, None):
                err_txt = (err or b"").decode("utf-8", errors="replace").strip()
                return {
                    "ok": False,
                    "error": (
                        f"PowerShell Start-Process failed ({proc.returncode}): {err_txt or 'no detail'}. "
                        f"Run manually: {script}"
                    ),
                }
            pid = None
        else:
            env = dict(launch_env)
            proc = subprocess.Popen(
                ["bash", str(script)],
                cwd=str(root),
                env=env,
                start_new_session=True,
            )
            method = "morkyn_launcher_sh"
            pid = proc.pid
    except Exception as exc:
        return {
            "ok": False,
            "error": (
                f"Failed to launch via Morkyn tools: {exc}. "
                f"Run: tools/morkyn_forge_api.bat with MORKYN_FORGE_ROOT set."
            ),
        }

    _last_launch_mono = time.monotonic()
    _last_launch = {
        "provider": provider,
        "pid": pid,
        "script": str(script),
        "cwd": str(root),
        "method": method,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "install_untouched": True,
    }
    msg = (
        f"Started {provider} via Morkyn launcher ({script.name}) — your Forge install files were not modified. "
        "Headless API (--api --nowebui). Wait for load, then Test connection. "
        "Generate reuses this instance if the API is already up."
    )
    return {
        "ok": True,
        **_last_launch,
        "message": msg,
        "already_running": False,
        "launched": True,
    }


# ---------------------------------------------------------------------------
# Installables (Forge / Comfy path-aware downloads)
# ---------------------------------------------------------------------------

FORGE_GITHUB = "https://github.com/lllyasviel/stable-diffusion-webui-forge"
COMFY_GITHUB = "https://github.com/comfyanonymous/ComfyUI"

# Catalog of optional pieces. status computed against forge_root / comfy_root.
# kind: root | path | file | git | pip
_IMAGE_INSTALLABLES: list[dict[str, Any]] = [
    {
        "id": "forge_app",
        "backend": "forge",
        "title": "Forge / ForgeSD install",
        "description": "Your Forge (or ForgeSD portable) folder. Required before any Forge downloads.",
        "kind": "root",
        "installable": False,
        "links": [
            {"label": "Forge GitHub", "url": FORGE_GITHUB},
            {
                "label": "Forge wiki",
                "url": "https://github.com/lllyasviel/stable-diffusion-webui-forge/wiki",
            },
        ],
    },
    {
        "id": "forge_controlnet_folder",
        "backend": "forge",
        "title": "ControlNet models folder",
        "description": "models/ControlNet under the Forge install (used by InstantID / FaceID).",
        "kind": "path",
        "rel_paths": ["models/ControlNet"],
        "create_if_missing": True,
        "installable": True,
        "links": [],
    },
    {
        "id": "forge_instantid_ipadapter",
        "backend": "forge",
        "title": "InstantID IP-Adapter (SD1.5)",
        "description": "Face identity adapter weights for ControlNet InstantID.",
        "kind": "file",
        "rel_paths": [
            "models/ControlNet/ip-adapter_instant_id_sd15.bin",
            "models/ControlNet/ip-adapter.bin",
        ],
        "installable": True,
        "download": {
            "type": "http",
            "url": "https://huggingface.co/InstantX/InstantID/resolve/main/ip-adapter.bin",
            "dest": "models/ControlNet/ip-adapter_instant_id_sd15.bin",
        },
        "links": [{"label": "InstantX/InstantID", "url": "https://huggingface.co/InstantX/InstantID"}],
    },
    {
        "id": "forge_instantid_controlnet",
        "backend": "forge",
        "title": "InstantID ControlNet (SD1.5)",
        "description": "ControlNet backbone for InstantID (~2.5 GB download).",
        "kind": "file",
        "rel_paths": [
            "models/ControlNet/control_instant_id_sd15.safetensors",
            "models/ControlNet/diffusion_pytorch_model.safetensors",
        ],
        "installable": True,
        "download": {
            "type": "http",
            "url": (
                "https://huggingface.co/InstantX/InstantID/resolve/main/"
                "ControlNetModel/diffusion_pytorch_model.safetensors"
            ),
            "dest": "models/ControlNet/control_instant_id_sd15.safetensors",
        },
        "links": [{"label": "InstantX/InstantID", "url": "https://huggingface.co/InstantX/InstantID"}],
    },
    {
        "id": "forge_faceid_sd15",
        "backend": "forge",
        "title": "IP-Adapter FaceID (SD1.5)",
        "description": "FaceID adapter for IP-Adapter Face modules.",
        "kind": "file",
        "rel_paths": [
            "models/ControlNet/ip-adapter-faceid_sd15.bin",
            "models/ipadapter/ip-adapter-faceid_sd15.bin",
        ],
        "installable": True,
        "download": {
            "type": "http",
            "url": "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sd15.bin",
            "dest": "models/ipadapter/ip-adapter-faceid_sd15.bin",
        },
        "links": [
            {"label": "IP-Adapter-FaceID", "url": "https://huggingface.co/h94/IP-Adapter-FaceID"},
        ],
    },
    {
        "id": "forge_faceid_plusv2",
        "backend": "forge",
        "title": "IP-Adapter FaceID Plus v2 (SD1.5)",
        "description": "Stronger FaceID Plus v2 weights.",
        "kind": "file",
        "rel_paths": [
            "models/ControlNet/ip-adapter-faceid-plusv2_sd15.bin",
            "models/ipadapter/ip-adapter-faceid-plusv2_sd15.bin",
        ],
        "installable": True,
        "download": {
            "type": "http",
            "url": (
                "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/"
                "ip-adapter-faceid-plusv2_sd15.bin"
            ),
            "dest": "models/ipadapter/ip-adapter-faceid-plusv2_sd15.bin",
        },
        "links": [
            {"label": "IP-Adapter-FaceID", "url": "https://huggingface.co/h94/IP-Adapter-FaceID"},
        ],
    },
    {
        "id": "forge_insightface_wheel",
        "backend": "forge",
        "title": "InsightFace wheel (Windows cp310)",
        "description": (
            "Installs insightface into Forge’s Python (needs Forge root + bundled 3.10). "
            "Required by InstantID / FaceID face analysis."
        ),
        "kind": "pip",
        "installable": True,
        "download": {
            "type": "pip",
            "url": (
                "https://github.com/Gourieff/Assets/raw/main/Insightface/"
                "insightface-0.7.3-cp310-cp310-win_amd64.whl"
            ),
            "package_hint": "insightface",
        },
        "links": [
            {
                "label": "InsightFace wheel",
                "url": "https://github.com/Gourieff/Assets/tree/main/Insightface",
            },
        ],
    },
    {
        "id": "forge_iib",
        "backend": "forge",
        "title": "Infinite Image Browsing (IIB)",
        "description": (
            "MIT-licensed gallery extension for Forge/A1111. Mørkyn embeds or opens it "
            "when installed — does not ship the extension source."
        ),
        "kind": "git",
        "rel_paths": [
            "extensions/sd-webui-infinite-image-browsing",
            "extensions/infinite-image-browsing",
        ],
        "installable": True,
        "download": {
            "type": "git",
            "url": "https://github.com/zanllp/sd-webui-infinite-image-browsing.git",
            "dest": "extensions/sd-webui-infinite-image-browsing",
        },
        "links": [
            {
                "label": "IIB GitHub (MIT)",
                "url": "https://github.com/zanllp/sd-webui-infinite-image-browsing",
            },
        ],
    },
    {
        "id": "comfy_app",
        "backend": "comfyui",
        "title": "ComfyUI install",
        "description": "Your ComfyUI folder. Required before Comfy downloads. (Comfy path is not fully verified in Mørkyn yet.)",
        "kind": "root",
        "installable": False,
        "links": [{"label": "ComfyUI GitHub", "url": COMFY_GITHUB}],
    },
    {
        "id": "comfy_ipadapter_plus",
        "backend": "comfyui",
        "title": "ComfyUI IPAdapter Plus",
        "description": "cubiq/ComfyUI_IPAdapter_plus custom node (FaceID / IP-Adapter workflows).",
        "kind": "git",
        "rel_paths": [
            "custom_nodes/ComfyUI_IPAdapter_plus",
            "ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus",
        ],
        "installable": True,
        "download": {
            "type": "git",
            "url": "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git",
            "dest": "custom_nodes/ComfyUI_IPAdapter_plus",
        },
        "links": [
            {
                "label": "ComfyUI_IPAdapter_plus",
                "url": "https://github.com/cubiq/ComfyUI_IPAdapter_plus",
            },
        ],
    },
    {
        "id": "comfy_instantid_node",
        "backend": "comfyui",
        "title": "ComfyUI InstantID node",
        "description": "cubiq InstantID custom node for ComfyUI.",
        "kind": "git",
        "rel_paths": [
            "custom_nodes/ComfyUI_InstantID",
            "ComfyUI/custom_nodes/ComfyUI_InstantID",
        ],
        "installable": True,
        "download": {
            "type": "git",
            "url": "https://github.com/cubiq/ComfyUI_InstantID.git",
            "dest": "custom_nodes/ComfyUI_InstantID",
        },
        "links": [
            {"label": "ComfyUI_InstantID", "url": "https://github.com/cubiq/ComfyUI_InstantID"},
            {"label": "InstantX/InstantID", "url": "https://huggingface.co/InstantX/InstantID"},
        ],
    },
]


def _resolve_backend_root(backend: str) -> dict[str, Any]:
    cfg = get_image_config()
    presets = load_image_presets()
    launch = presets.get("launch") if isinstance(presets.get("launch"), dict) else {}
    if backend == "forge":
        raw = str(cfg.get("forge_root") or launch.get("forge_root") or "").strip()
        valid = validate_backend_root("forge", raw) if raw else {"ok": False, "message": "Forge root not set."}
        return {"backend": "forge", "root": raw, "valid": bool(valid.get("ok")), "message": valid.get("message") or ""}
    raw = str(cfg.get("comfy_root") or launch.get("comfy_root") or "").strip()
    valid = validate_backend_root("comfyui", raw) if raw else {"ok": False, "message": "ComfyUI root not set."}
    # Prefer nested ComfyUI/ if portable pack
    path = Path(raw) if raw else None
    if path and (path / "ComfyUI" / "main.py").is_file():
        return {
            "backend": "comfyui",
            "root": str(path / "ComfyUI"),
            "valid": True,
            "message": "Using nested ComfyUI folder.",
        }
    return {
        "backend": "comfyui",
        "root": raw,
        "valid": bool(valid.get("ok")),
        "message": valid.get("message") or "",
    }


def _forge_layout(root: str) -> dict[str, Path]:
    """Map pack root vs webui-only root to models / python paths."""
    base = Path(root)
    webui = base
    if (base / "webui").is_dir() and (
        (base / "webui" / "webui-user.bat").is_file()
        or (base / "webui" / "modules_forge").is_dir()
        or (base / "webui" / "webui.py").is_file()
    ):
        webui = base / "webui"
    models = webui / "models"
    if not models.is_dir() and (base / "models").is_dir():
        models = base / "models"
    py_candidates = [
        base / "system" / "python" / "python.exe",
        base / "python" / "python.exe",
        webui / "venv" / "Scripts" / "python.exe",
        base / "venv" / "Scripts" / "python.exe",
        webui / "venv" / "bin" / "python",
        base / "venv" / "bin" / "python",
    ]
    python = next((p for p in py_candidates if p.is_file()), None)
    return {"base": base, "webui": webui, "models": models, "python": python}


def _path_under_root(root: Path, rel: str) -> Path:
    rel_n = str(rel or "").replace("\\", "/").lstrip("/")
    return (root / rel_n).resolve()


def _installable_present(item: dict[str, Any], root_info: dict[str, Any]) -> tuple[bool, str]:
    if not root_info.get("valid") or not root_info.get("root"):
        return False, "Install root not set"
    root = Path(str(root_info["root"]))
    layout = _forge_layout(str(root)) if item.get("backend") == "forge" else {
        "base": root,
        "webui": root,
        "models": root / "models",
        "python": None,
    }
    kind = item.get("kind")
    if kind == "root":
        return True, str(root)
    if kind == "pip":
        # Fast disk check only — never import Forge's Python (can hang or take minutes).
        py = layout.get("python")
        if not py or not Path(py).is_file():
            return False, "Forge Python not found"
        search_roots = [
            Path(py).parent.parent / "Lib" / "site-packages",
            Path(py).parent / "Lib" / "site-packages",
            layout["webui"] / "venv" / "Lib" / "site-packages",
            layout["base"] / "venv" / "Lib" / "site-packages",
            layout["base"] / "system" / "python" / "Lib" / "site-packages",
        ]
        for site in search_roots:
            try:
                if (site / "insightface").is_dir() or (site / "insightface-0.7.3.dist-info").is_dir():
                    return True, str(site / "insightface")
                # dist-info folder name variants
                if site.is_dir():
                    for child in site.iterdir():
                        name = child.name.lower()
                        if name.startswith("insightface") and (
                            child.is_dir() or name.endswith(".dist-info")
                        ):
                            return True, str(child)
            except OSError:
                continue
        return False, "insightface package not found under Forge Python"
    # file / path / git: any rel_path exists (and non-empty for files)
    for rel in item.get("rel_paths") or []:
        # Try webui-relative and base-relative
        candidates = [
            _path_under_root(layout["webui"], rel),
            _path_under_root(layout["base"], rel),
        ]
        if rel.startswith("models/"):
            candidates.append(layout["models"] / rel.split("models/", 1)[1])
        for cand in candidates:
            try:
                if cand.is_dir() and any(cand.iterdir()):
                    return True, str(cand)
                if cand.is_dir() and item.get("kind") == "path":
                    return True, str(cand)
                if cand.is_file() and cand.stat().st_size > 1024:
                    return True, str(cand)
            except OSError:
                continue
    return False, ""


def list_image_installables() -> dict[str, Any]:
    """Checklist of Forge/Comfy pieces + installed status (disk)."""
    forge = _resolve_backend_root("forge")
    comfy = _resolve_backend_root("comfyui")
    items_out: list[dict[str, Any]] = []
    for raw in _IMAGE_INSTALLABLES:
        item = dict(raw)
        backend = str(item.get("backend") or "")
        root_info = forge if backend == "forge" else comfy
        root_ok = bool(root_info.get("valid"))
        installed, detail = _installable_present(item, root_info)
        can_install = bool(item.get("installable")) and root_ok and not installed
        if item.get("kind") == "root":
            installed = root_ok
            detail = root_info.get("root") or root_info.get("message") or ""
            can_install = False
        status = "installed" if installed else ("blocked" if not root_ok else "missing")
        items_out.append(
            {
                "id": item["id"],
                "backend": backend,
                "title": item.get("title"),
                "description": item.get("description"),
                "kind": item.get("kind"),
                "status": status,
                "installed": installed,
                "installable": bool(item.get("installable")),
                "can_install": can_install,
                "detail": detail,
                "links": list(item.get("links") or []),
                "blocked_reason": (
                    None
                    if root_ok
                    else f"Set {backend} install root first (LLM Settings → Images)."
                ),
            }
        )
    return {
        "ok": True,
        "forge": forge,
        "comfyui": comfy,
        "repos": {
            "forge": FORGE_GITHUB,
            "comfyui": COMFY_GITHUB,
            "instantid": "https://huggingface.co/InstantX/InstantID",
            "ipadapter_plus": "https://github.com/cubiq/ComfyUI_IPAdapter_plus",
        },
        "note": (
            "ForgeSD is the currently tested image path. ComfyUI hooks exist but are "
            "not fully verified in Mørkyn yet — mark verified once someone confirms."
        ),
        "items": items_out,
    }


def _download_http_file(url: str, dest: Path, *, timeout: float = 600.0) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Morkyn/image-installables"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = 0
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
                total += len(chunk)
    tmp.replace(dest)
    return {"ok": True, "path": str(dest), "bytes": total}


def _git_clone(url: str, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return {"ok": True, "path": str(dest), "already": True}
    try:
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "git not found on PATH. Install Git or clone manually."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "git clone failed")[:500],
        }
    return {"ok": True, "path": str(dest)}


def _pip_install_forge(root: str, package_url: str) -> dict[str, Any]:
    layout = _forge_layout(root)
    py = layout.get("python")
    if not py or not Path(py).is_file():
        return {
            "ok": False,
            "error": "Could not find Forge Python (system/python or venv). Install insightface manually.",
        }
    try:
        proc = subprocess.run(
            [str(py), "-m", "pip", "install", package_url, "--prefer-binary"],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "pip failed")[:800],
            "python": str(py),
        }
    return {"ok": True, "python": str(py), "log": (proc.stdout or "")[-400:]}


def install_image_component(component_id: str) -> dict[str, Any]:
    """
    Download/install one catalog entry into the matching backend root.
    Refuses if root is missing/invalid or already installed.
    """
    item = next((x for x in _IMAGE_INSTALLABLES if x.get("id") == component_id), None)
    if not item:
        return {"ok": False, "error": f"Unknown installable id: {component_id}"}
    if not item.get("installable"):
        return {
            "ok": False,
            "error": "This item is not auto-installable. Follow the GitHub link and set the folder path.",
            "links": item.get("links") or [],
        }
    backend = str(item.get("backend") or "")
    root_info = _resolve_backend_root(backend)
    if not root_info.get("valid") or not root_info.get("root"):
        return {
            "ok": False,
            "error": f"Set a valid {backend} install root first (LLM Settings → Images).",
            "blocked": True,
        }
    installed, detail = _installable_present(item, root_info)
    if installed:
        return {"ok": True, "status": "installed", "detail": detail, "already": True}

    root = Path(str(root_info["root"]))
    layout = _forge_layout(str(root)) if backend == "forge" else {
        "base": root,
        "webui": root,
        "models": root / "models",
        "python": None,
    }
    # Create empty ControlNet folder
    if item.get("id") == "forge_controlnet_folder" or item.get("create_if_missing"):
        for rel in item.get("rel_paths") or []:
            target = layout["models"] / rel.split("models/", 1)[-1] if rel.startswith("models/") else layout["webui"] / rel
            target.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "status": "installed", "detail": "Folder ready", "id": item["id"]}

    dl = item.get("download") or {}
    dtype = str(dl.get("type") or "")
    try:
        if dtype == "http":
            dest_rel = str(dl.get("dest") or "")
            if dest_rel.startswith("models/"):
                dest = layout["models"] / dest_rel.split("models/", 1)[1]
            else:
                dest = layout["webui"] / dest_rel
            result = _download_http_file(str(dl.get("url") or ""), dest)
            if not result.get("ok"):
                return result
            return {
                "ok": True,
                "status": "installed",
                "id": item["id"],
                "path": result.get("path"),
                "bytes": result.get("bytes"),
            }
        if dtype == "git":
            dest_rel = str(dl.get("dest") or "").replace("\\", "/").lstrip("/")
            # Forge extensions live under the webui root (portable packs: base/webui/extensions).
            if backend == "forge" and dest_rel.startswith("extensions/"):
                dest = layout["webui"] / dest_rel
            else:
                dest = layout["base"] / dest_rel
            result = _git_clone(str(dl.get("url") or ""), dest)
            if not result.get("ok"):
                return result
            return {"ok": True, "status": "installed", "id": item["id"], **result}
        if dtype == "pip":
            result = _pip_install_forge(str(root), str(dl.get("url") or ""))
            if not result.get("ok"):
                return result
            return {"ok": True, "status": "installed", "id": item["id"], **result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:500], "id": item["id"]}

    return {"ok": False, "error": f"No download handler for kind={dtype or item.get('kind')}"}


# ---------------------------------------------------------------------------
# Dual character generation (face + fullbody)
# ---------------------------------------------------------------------------


def build_character_prompt(
    *,
    kind: str = "face",
    name: str = "",
    title: str = "",
    known_as: str = "",
    backstory: str = "",
    world_style: str = "",
    extra: str = "",
    equipment: list[str] | str | None = None,
    hair: str = "",
    facial_features: str = "",
    appearance: str = "",
    level: int | str | None = None,
    injuries: list[str] | str | None = None,
    age: str = "",
    sex: str = "",
    visibility_mode: str = "full",
    visibility_note: str = "",
    observed_description: str = "",
    location: str = "",
) -> str:
    """
    Shared simple tag prompt for face and fullbody.

    Order: subject → setting → pose → hair → face → clothing → image-type
    Face vs body only swap pose / (portrait) vs (full body + feet).
    """
    return build_portrait_prompt(
        name=name,
        title=title,
        known_as=known_as,
        backstory=backstory,
        world_style=world_style,
        extra=extra,
        style="",
        equipment=equipment,
        hair=hair,
        facial_features=facial_features,
        appearance=appearance,
        level=level,
        injuries=injuries,
        age=age,
        sex=sex,
        visibility_mode=visibility_mode,
        visibility_note=visibility_note,
        observed_description=observed_description,
        kind=kind,
        location=location,
    )


def _store_setting_json(key: str, value: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=True)),
        )


def build_character_prompt_pack(
    *,
    name: str = "",
    title: str = "",
    known_as: str = "",
    backstory: str = "",
    world_style: str = "",
    extra: str = "",
    equipment: list[str] | None = None,
    hair: str = "",
    facial_features: str = "",
    appearance: str = "",
    injuries: list[str] | None = None,
    level: int | str | None = None,
    age: str = "",
    sex: str = "",
    visibility_note: str = "",
    observed_description: str = "",
    subject: str = "player",
    loras: list[Any] | None = None,
    negative_override: str = "",
    kinds: list[str] | None = None,
    location: str = "",
) -> dict[str, Any]:
    """
    Build the final Forge-bound prompts for face / fullbody without generating.

    Identity fields are only *read* here — they are never written back.
    Players can copy/edit the returned strings in the UI, then send them as overrides.

    Final positive order:
      [optional primary theme], core tags…, <lora:…>  (LoRAs always last)
    """
    cfg = get_image_config()
    presets = load_image_presets()
    shared = presets.get("shared") if isinstance(presets.get("shared"), dict) else {}
    equipment = list(equipment or [])
    injuries = list(injuries or [])
    loras = list(loras or [])
    primary = str(cfg.get("primary_prompt") or "").strip()
    primary_neg = str(cfg.get("primary_negative") or "").strip()
    base_negative = str(
        negative_override
        or shared.get("negative_prompt")
        or cfg.get("negative_prompt")
        or ""
    ).strip()
    if primary_neg and primary_neg not in base_negative:
        base_negative = f"{base_negative}, {primary_neg}" if base_negative else primary_neg

    # Never feed backstory into visibility for self-portraits — it is biography, not a glimpse note.
    subject_l = str(subject or "player").strip().lower() or "player"
    observed_for_vis = _norm_text(observed_description)
    if subject_l != "player" and not observed_for_vis:
        # NPC/other: only use observed text, not full backstory essays
        observed_for_vis = ""
    vis = infer_visibility_mode(
        visibility_note=visibility_note,
        observed_description=observed_for_vis,
        summary="" if subject_l == "player" else _norm_text(backstory)[:200],
        subject=subject_l,
    )
    vis_mode = str(vis.get("mode") or "full")
    vis_note = str(vis.get("visibility_note") or visibility_note or "")
    observed = observed_for_vis
    location = _norm_text(location)

    want = [str(k).lower() for k in (kinds or ["face", "fullbody"])]
    normalized: list[str] = []
    for k in want:
        if k in {"face", "portrait", "bust", "head"} and "face" not in normalized:
            normalized.append("face")
        elif k in {"fullbody", "body", "full", "full_body"} and "fullbody" not in normalized:
            normalized.append("fullbody")
        elif k == "both":
            if "face" not in normalized:
                normalized.append("face")
            if "fullbody" not in normalized:
                normalized.append("fullbody")
    if not normalized:
        normalized = ["face", "fullbody"]
    if vis_mode == "partial":
        normalized = [k for k in normalized if k == "face"] or ["face"]

    lora_tags = format_lora_tags(loras)

    def _finalize(subject_prompt: str) -> str:
        # Optional primary theme first, core tags, LoRAs last (after a comma).
        core = str(subject_prompt or "").strip()
        if primary and primary.lower() not in core.lower():
            core = f"{primary}, {core}" if core else primary
        if lora_tags:
            return f"{core}, {lora_tags}" if core else lora_tags
        return core

    face_subject = build_character_prompt(
        kind="face",
        name=name,
        title=title,
        known_as=known_as,
        backstory=backstory,
        world_style=world_style,
        extra=extra,
        equipment=equipment,
        hair=hair,
        facial_features=facial_features,
        appearance=appearance,
        level=level,
        injuries=injuries,
        age=age,
        sex=sex,
        visibility_mode=vis_mode,
        visibility_note=vis_note,
        observed_description=observed,
        location=location,
    )
    body_subject = build_character_prompt(
        kind="fullbody",
        name=name,
        title=title,
        known_as=known_as,
        backstory=backstory,
        world_style=world_style,
        extra=extra,
        equipment=equipment,
        hair=hair,
        facial_features=facial_features,
        appearance=appearance,
        level=level,
        injuries=injuries,
        age=age,
        sex=sex,
        visibility_mode=vis_mode,
        visibility_note=vis_note,
        observed_description=observed,
        location=location,
    )

    face_final = _finalize(face_subject)
    body_final = _finalize(body_subject)
    face_prof = presets.get("face") if isinstance(presets.get("face"), dict) else {}
    body_prof = presets.get("fullbody") if isinstance(presets.get("fullbody"), dict) else {}
    face_extra_neg = str(face_prof.get("negative_extra") or "").strip()
    body_extra_neg = str(body_prof.get("negative_extra") or "").strip()
    face_neg = (
        f"{base_negative}, {face_extra_neg}"
        if face_extra_neg and base_negative
        else (face_extra_neg or base_negative)
    )
    # Body uses the same light shared negative; optional preset negative_extra only if set.
    # Do not inject “legs out of frame” — let (full body:1.7) carry framing.
    body_neg = (
        f"{base_negative}, {body_extra_neg}"
        if body_extra_neg and base_negative
        else (body_extra_neg or base_negative)
    )
    if vis_mode == "partial":
        extra_neg = "full body character sheet"
        face_neg = f"{face_neg}, {extra_neg}" if face_neg else extra_neg

    return {
        "ok": True,
        "kinds": normalized,
        "visibility_mode": vis_mode,
        "visibility_note": vis_note,
        "face_prompt": face_final,
        "fullbody_prompt": body_final,
        "face_negative": face_neg,
        "fullbody_negative": body_neg,
        "negative": base_negative,
        "loras": loras,
        "lora_tags": lora_tags,
        "layers": {
            "primary": primary,
            "primary_negative": primary_neg,
            "extra": _norm_text(extra),
            "location": location,
            "face_subject": face_subject,
            "fullbody_subject": body_subject,
            "identity": {
                "name": name,
                "title": title,
                "known_as": known_as,
                "age": age,
                "sex": sex,
                "world_style": world_style,
                "location": location,
                "backstory": _norm_text(backstory)[:280],
            },
        },
        "note": (
            "Simple ordered tags: subject, setting, pose, hair, clothes, image-type, "
            "then LoRAs. Face/body only differ on pose and framing. "
            "Editing the engine box only changes what is sent to Forge."
        ),
    }


def store_player_art_assets(
    *,
    face: dict[str, Any] | None = None,
    fullbody: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    meta = meta or {}
    if face and face.get("data_url"):
        _store_setting_json(
            PLAYER_PORTRAIT_KEY,
            {
                "data_url": face.get("data_url"),
                "path": face.get("path") or "",
                "prompt": str(face.get("prompt") or "")[:8000],
                "seed": face.get("seed"),
                "kind": "face",
                "equipment": meta.get("equipment") or [],
                "level": meta.get("level"),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
    if fullbody and fullbody.get("data_url"):
        _store_setting_json(
            PLAYER_FULLBODY_KEY,
            {
                "data_url": fullbody.get("data_url"),
                "path": fullbody.get("path") or "",
                "prompt": str(fullbody.get("prompt") or "")[:8000],
                "seed": fullbody.get("seed"),
                "kind": "fullbody",
                "equipment": meta.get("equipment") or [],
                "level": meta.get("level"),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )


def generate_character_set(
    *,
    name: str = "",
    title: str = "",
    known_as: str = "",
    backstory: str = "",
    world_style: str = "",
    extra: str = "",
    equipment: list[str] | None = None,
    hair: str = "",
    facial_features: str = "",
    appearance: str = "",
    injuries: list[str] | None = None,
    level: int | str | None = None,
    age: str = "",
    sex: str = "",
    kinds: list[str] | None = None,
    seed: int | None = None,
    launch_if_offline: bool = True,
    persist: bool = False,
    visibility_note: str = "",
    observed_description: str = "",
    subject: str = "player",
    skip_subject_gate: bool = False,
    loras: list[Any] | None = None,
    use_face_reference: bool | None = None,
    reference_data_url: str = "",
    negative_override: str = "",
    face_prompt: str = "",
    fullbody_prompt: str = "",
    face_negative: str = "",
    fullbody_negative: str = "",
) -> dict[str, Any]:
    """
    Generate face and/or fullbody images using presets.

    launch_if_offline: discover/hook existing API first; only then start one backend.
    Full body prefers face img2img reference when a face image is available.
    Partial visibility forces glimpse-only art (no invented full body sheet).

    face_prompt / fullbody_prompt: when set, used as the final Forge positive (player-edited).
    """
    started = time.time()
    equipment = list(equipment or [])
    injuries = list(injuries or [])
    loras = list(loras or [])
    # Preserve full engine prompts — only trim ends (do not collapse/clip body text).
    face_prompt = str(face_prompt or "").strip()
    fullbody_prompt = str(fullbody_prompt or "").strip()
    face_negative = str(face_negative or "").strip()
    fullbody_negative = str(fullbody_negative or "").strip()
    cfg = get_image_config()

    subject_gate = assess_character_art_readiness(
        name=name,
        title=title,
        known_as=known_as,
        backstory=backstory,
        world_style=world_style,
        extra=extra,
        age=age,
        sex=sex,
        equipment=equipment,
        injuries=injuries,
        visibility_note=visibility_note,
        observed_description=observed_description,
        subject=subject,
        require_backend=True,
    )
    if not skip_subject_gate and not subject_gate.get("can_generate"):
        return {
            "ok": False,
            "error": subject_gate.get("message") or "Not enough info to generate character art.",
            "missing": subject_gate.get("missing") or [],
            "warnings": subject_gate.get("warnings") or [],
            "subject_readiness": subject_gate,
            "visibility_mode": subject_gate.get("visibility_mode"),
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    # Hook first (discover ports), then optional single launch.
    readiness = image_readiness(launch_if_offline=bool(launch_if_offline))
    if not readiness.get("api_ok"):
        return {
            "ok": False,
            "error": "Image backend not ready.",
            "readiness": readiness,
            "subject_readiness": subject_gate,
            "missing": readiness.get("missing") or [],
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    presets = load_image_presets()
    shared = presets.get("shared") if isinstance(presets.get("shared"), dict) else {}
    vis_mode = str(subject_gate.get("visibility_mode") or "full")
    vis_note = str(subject_gate.get("visibility_note") or visibility_note or "")
    observed = _norm_text(observed_description) or _norm_text(backstory)

    # Prefer caller kinds, but never exceed what visibility allows.
    allowed = list(subject_gate.get("recommended_kinds") or ["face", "fullbody"])
    want = [str(k).lower() for k in (kinds or allowed)]
    normalized: list[str] = []
    for k in want:
        if k in {"face", "portrait", "bust", "head"}:
            if "face" not in normalized and ("face" in allowed or subject == "player"):
                if "face" in allowed or subject == "player":
                    normalized.append("face")
        elif k in {"fullbody", "body", "full", "full_body"}:
            if "fullbody" not in normalized and ("fullbody" in allowed or subject == "player"):
                if "fullbody" in allowed or (subject == "player" and vis_mode == "full"):
                    normalized.append("fullbody")
    if not normalized:
        normalized = list(allowed) if allowed else ["face"]
    # Partial visibility: never emit fullbody studio art.
    if vis_mode == "partial":
        normalized = [k for k in normalized if k == "face"] or ["face"]

    if seed is None:
        seed = int(time.time() * 1000) % (2**31 - 1)
    share = bool(shared.get("share_seed_base", True))
    negative = str(
        negative_override
        or shared.get("negative_prompt")
        or cfg.get("negative_prompt")
        or ""
    )
    # For partial glimpses, discourage inventing a clean portrait.
    if vis_mode == "partial":
        negative = (
            (negative + ", ") if negative else ""
        ) + "full body character sheet, studio portrait, clear unobscured face if face not visible, invented clothing details"

    use_ref = (
        bool(cfg.get("fullbody_use_face_ref", True))
        if use_face_reference is None
        else bool(use_face_reference)
    )
    ref_url = str(reference_data_url or "").strip()
    # Denoise: lower = stronger ref / composition lock; higher = freer full-body pose.
    # Face is composited into a tall canvas — default ~0.88 keeps likeness without bust crop.
    try:
        ref_denoise = float(cfg.get("fullbody_ref_denoise") or 0.88)
    except (TypeError, ValueError):
        ref_denoise = 0.88
    # Soften old strong saves (≤0.72) that glued body gens to portrait composition.
    if ref_denoise <= 0.72:
        ref_denoise = 0.88
    ref_denoise = max(0.75, min(0.95, ref_denoise))

    results: dict[str, Any] = {
        "ok": True,
        "readiness": readiness,
        "subject_readiness": subject_gate,
        "kinds": normalized,
        "visibility_mode": vis_mode,
        "visibility_note": vis_note,
        "loras": loras,
        "use_face_reference": use_ref,
        "ref_denoise": ref_denoise,
    }

    def _stored_player_url(setting_key: str) -> str:
        try:
            with connect() as conn:
                row = conn.execute(
                    "SELECT value FROM settings WHERE key = ?",
                    (setting_key,),
                ).fetchone()
            if row:
                stored = json.loads(row["value"])
                if isinstance(stored, dict) and stored.get("data_url"):
                    return str(stored["data_url"])
        except Exception:
            return ""
        return ""

    for index, kind in enumerate(normalized):
        profile = presets.get(kind) if isinstance(presets.get(kind), dict) else {}
        # Prefer player-edited engine prompts when provided.
        use_final = False
        if kind == "face" and face_prompt:
            prompt = face_prompt
            use_final = True
        elif kind == "fullbody" and fullbody_prompt:
            prompt = fullbody_prompt
            use_final = True
        else:
            prompt = build_character_prompt(
                kind=kind,
                name=name,
                title=title,
                known_as=known_as,
                backstory=backstory,
                world_style=world_style,
                extra=extra,
                equipment=equipment,
                hair=hair,
                facial_features=facial_features,
                appearance=appearance,
                level=level,
                injuries=injuries,
                age=age,
                sex=sex,
                visibility_mode=vis_mode,
                visibility_note=vis_note,
                observed_description=observed,
            )
        kind_seed = int(seed) + (0 if share else index) if share else int(seed) + index * 17
        if share and kind == "fullbody":
            kind_seed = int(seed) + 1

        kind_negative = negative
        if kind == "face" and face_negative:
            kind_negative = face_negative
        elif kind == "fullbody" and fullbody_negative:
            kind_negative = fullbody_negative

        init_image = None
        denoise = None
        face_lock = None
        cons = resolve_character_consistency_mode(cfg)
        # Cross-ref: body ← face if face exists first; face ← body if body exists first.
        face_from_run = results.get("face") if isinstance(results.get("face"), dict) else None
        body_from_run = results.get("fullbody") if isinstance(results.get("fullbody"), dict) else None
        sibling = None
        if kind == "fullbody":
            if face_from_run and face_from_run.get("data_url"):
                sibling = str(face_from_run.get("data_url"))
            elif ref_url:
                sibling = ref_url
            else:
                sibling = _stored_player_url(PLAYER_PORTRAIT_KEY) or None
        elif kind == "face":
            if body_from_run and body_from_run.get("data_url"):
                sibling = str(body_from_run.get("data_url"))
            elif ref_url:
                sibling = ref_url
            else:
                sibling = _stored_player_url(PLAYER_FULLBODY_KEY) or None

        body_w = int(profile.get("width") or (512 if kind == "face" else 576))
        body_h = int(profile.get("height") or (512 if kind == "face" else 768))
        used_composite = False
        if sibling and use_ref:
            if cons.get("use_strong"):
                face_lock = sibling
            elif cons.get("use_light_img2img") or cons.get("mode") == "light":
                if kind == "fullbody":
                    # Never stretch a face portrait to full body size — place face in upper canvas.
                    composited = _composite_face_ref_for_fullbody(
                        sibling, width=body_w, height=body_h
                    )
                    if composited:
                        init_image = f"data:image/png;base64,{composited}"
                        used_composite = True
                        denoise = max(ref_denoise, 0.84)
                    else:
                        # Fallback: still use face but force high denoise so pose can break free.
                        init_image = sibling
                        denoise = max(ref_denoise, 0.90)
                else:
                    init_image = sibling
                    denoise = min(0.85, ref_denoise + 0.06)

        if kind == "fullbody":
            kind_negative = _fullbody_negative(kind_negative)

        gen = generate_image(
            prompt=prompt,
            negative_prompt=kind_negative,
            width=body_w,
            height=body_h,
            steps=int(profile.get("steps") or 24),
            cfg_scale=float(profile.get("cfg_scale") or 7),
            seed=kind_seed,
            purpose=f"character_{kind}",
            loras=[] if use_final else loras,
            init_image=init_image,
            denoising_strength=denoise,
            apply_primary=not use_final,
            apply_loras=not use_final,
            face_lock_image=face_lock,
            consistency_mode=str(cfg.get("character_consistency") or "auto"),
        )
        gen["kind"] = kind
        gen["built_prompt"] = gen.get("prompt") or prompt
        gen["used_face_reference"] = bool(init_image or face_lock)
        gen["face_ref_composited"] = bool(used_composite)
        gen["prompt_was_override"] = use_final
        results[kind] = gen
        if not gen.get("ok"):
            results["ok"] = False
            results["error"] = gen.get("error") or f"{kind} generation failed"
            break

    if persist and results.get("ok"):
        try:
            store_player_art_assets(
                face=results.get("face") if isinstance(results.get("face"), dict) else None,
                fullbody=results.get("fullbody") if isinstance(results.get("fullbody"), dict) else None,
                meta={"equipment": equipment, "level": level, "visibility_mode": vis_mode},
            )
        except Exception as exc:
            results["persist_error"] = str(exc)

    results["elapsed_ms"] = int((time.time() - started) * 1000)
    results["equipment_used"] = equipment
    results["injuries_used"] = injuries
    return results
