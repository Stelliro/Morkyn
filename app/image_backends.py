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
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from app.db import connect

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = Path(__file__).resolve().parent / "comfy_workflows"
PORTRAIT_DIR = ROOT / "data" / "portraits"

# Defaults match common local installs.
DEFAULT_FORGE_URL = "http://127.0.0.1:7860"
DEFAULT_COMFY_URL = "http://127.0.0.1:8188"

IMAGE_CONFIG_KEY = "image_config"


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
        "provider": _env("AI_RPG_IMAGE_PROVIDER", "off"),  # off | forge | comfyui
        "forge_base_url": _env("AI_RPG_FORGE_URL", DEFAULT_FORGE_URL),
        "comfy_base_url": _env("AI_RPG_COMFY_URL", DEFAULT_COMFY_URL),
        "comfy_checkpoint": _env("AI_RPG_COMFY_CHECKPOINT", ""),
        "comfy_workflow": _env("AI_RPG_COMFY_WORKFLOW", "txt2img_api.json"),
        "default_width": _env_int("AI_RPG_IMAGE_WIDTH", 512),
        "default_height": _env_int("AI_RPG_IMAGE_HEIGHT", 512),
        "default_steps": _env_int("AI_RPG_IMAGE_STEPS", 20),
        "default_cfg": float(_env("AI_RPG_IMAGE_CFG", "7") or 7),
        "negative_prompt": _env(
            "AI_RPG_IMAGE_NEGATIVE",
            "lowres, blurry, deformed, bad anatomy, watermark, text, logo",
        ),
        "portrait_style": _env(
            "AI_RPG_PORTRAIT_STYLE",
            "pixel art portrait, 8-bit style, limited palette, front view, bust, clean silhouette, game sprite",
        ),
        "timeout_seconds": _env_int("AI_RPG_IMAGE_TIMEOUT", 180),
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
        "portrait_style",
        "default_width",
        "default_height",
        "default_steps",
        "default_cfg",
        "timeout_seconds",
    }
    next_cfg = {**current}
    for key in allowed:
        if key not in payload:
            continue
        if key in {"default_width", "default_height", "default_steps", "timeout_seconds"}:
            try:
                next_cfg[key] = int(payload.get(key))
            except (TypeError, ValueError):
                continue
        elif key == "default_cfg":
            try:
                next_cfg[key] = float(payload.get(key))
            except (TypeError, ValueError):
                continue
        else:
            next_cfg[key] = str(payload.get(key) or "").strip()
    next_cfg["provider"] = _normalize_provider(next_cfg.get("provider"))
    next_cfg["default_width"] = max(64, min(2048, int(next_cfg.get("default_width") or 512)))
    next_cfg["default_height"] = max(64, min(2048, int(next_cfg.get("default_height") or 512)))
    next_cfg["default_steps"] = max(1, min(150, int(next_cfg.get("default_steps") or 20)))
    next_cfg["timeout_seconds"] = max(10, min(900, int(next_cfg.get("timeout_seconds") or 180)))
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
    cfg["enabled"] = cfg["provider"] in {"forge", "comfyui"}
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


def probe_image_backend(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = get_image_config() if config is None else config
    provider = _normalize_provider(cfg.get("provider"))
    if provider == "off":
        return {
            "ok": True,
            "provider": "off",
            "message": "Image backend is off. Choose Forge or ComfyUI in settings when you want local art.",
        }
    try:
        if provider == "forge":
            base = str(cfg.get("forge_base_url") or DEFAULT_FORGE_URL).rstrip("/")
            # Lightweight endpoints — either works on Forge/A1111.
            try:
                payload = _http_json("GET", f"{base}/sdapi/v1/sd-models", timeout=8)
                count = len(payload) if isinstance(payload, list) else 0
                return {
                    "ok": True,
                    "provider": "forge",
                    "base_url": base,
                    "message": f"Forge/A1111 reachable — {count} checkpoint(s) listed.",
                    "models": count,
                }
            except Exception:
                _http_json("GET", f"{base}/sdapi/v1/options", timeout=8)
                return {
                    "ok": True,
                    "provider": "forge",
                    "base_url": base,
                    "message": "Forge/A1111 reachable (options).",
                }
        if provider == "comfyui":
            base = str(cfg.get("comfy_base_url") or DEFAULT_COMFY_URL).rstrip("/")
            payload = _http_json("GET", f"{base}/system_stats", timeout=8)
            return {
                "ok": True,
                "provider": "comfyui",
                "base_url": base,
                "message": "ComfyUI reachable.",
                "system_stats": payload if isinstance(payload, dict) else {},
            }
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "message": str(exc),
        }
    return {"ok": False, "provider": provider, "message": "Unknown provider"}


def build_portrait_prompt(
    *,
    name: str = "",
    title: str = "",
    known_as: str = "",
    backstory: str = "",
    world_style: str = "",
    extra: str = "",
    style: str = "",
) -> str:
    cfg = get_image_config()
    style_bit = (style or str(cfg.get("portrait_style") or "")).strip()
    parts = [style_bit] if style_bit else []
    who = name or known_as or "adventurer"
    parts.append(f"character named {who}")
    if title:
        parts.append(f"title {title}")
    if known_as and known_as != who:
        parts.append(f"also known as {known_as}")
    if world_style:
        parts.append(f"setting: {world_style}")
    if backstory:
        # Keep short so local UIs don't choke.
        snippet = " ".join(str(backstory).split())[:280]
        parts.append(snippet)
    if extra:
        parts.append(str(extra).strip()[:200])
    return ", ".join(p for p in parts if p)


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
) -> dict[str, Any]:
    """
    Generate one image. Returns:
      ok, provider, mime, image_base64, data_url, path (if saved), seed, elapsed_ms, error?
    """
    cfg = get_image_config()
    provider = _normalize_provider(cfg.get("provider"))
    if provider == "off":
        return {
            "ok": False,
            "provider": "off",
            "error": "Image backend is off. Set provider to forge or comfyui in Image settings.",
        }
    prompt = str(prompt or "").strip()
    if not prompt:
        return {"ok": False, "provider": provider, "error": "Prompt is empty."}

    width = int(width or cfg.get("default_width") or 512)
    height = int(height or cfg.get("default_height") or 512)
    steps = int(steps or cfg.get("default_steps") or 20)
    cfg_scale = float(cfg_scale if cfg_scale is not None else cfg.get("default_cfg") or 7)
    negative = (
        negative_prompt
        if negative_prompt is not None
        else str(cfg.get("negative_prompt") or "")
    )
    if seed is None:
        seed = int(time.time() * 1000) % (2**31 - 1)
    timeout = int(cfg.get("timeout_seconds") or 180)
    started = time.time()

    try:
        if provider == "forge":
            result = _generate_forge(
                base_url=str(cfg.get("forge_base_url") or DEFAULT_FORGE_URL),
                prompt=prompt,
                negative_prompt=negative,
                width=width,
                height=height,
                steps=steps,
                cfg_scale=cfg_scale,
                seed=int(seed),
                timeout=timeout,
            )
        elif provider == "comfyui":
            result = _generate_comfy(
                base_url=str(cfg.get("comfy_base_url") or DEFAULT_COMFY_URL),
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


def _save_image_bytes(data: bytes, *, purpose: str, mime: str) -> str:
    PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".png" if "png" in mime else ".jpg"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in purpose)[:40] or "img"
    name = f"{safe}-{int(time.time())}-{uuid.uuid4().hex[:8]}{ext}"
    path = PORTRAIT_DIR / name
    path.write_bytes(data)
    # Relative path for UI / API consumers
    return str(path.relative_to(ROOT)).replace("\\", "/")


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
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    body = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": cfg_scale,
        "seed": seed,
        "batch_size": 1,
        "n_iter": 1,
        "sampler_name": "Euler a",
    }
    payload = _http_json("POST", f"{base}/sdapi/v1/txt2img", body=body, timeout=timeout)
    images = payload.get("images") if isinstance(payload, dict) else None
    if not images:
        raise RuntimeError("Forge/A1111 returned no images. Is --api enabled?")
    # A1111 sometimes appends metadata after a comma in the base64 field.
    raw = str(images[0]).split(",", 1)[0]
    return {"image_base64": raw, "mime": "image/png", "raw": payload}


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
