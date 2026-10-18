"""Play Mørkyn through its cloud-API path with an agent answering every model call.

    python tools/api_bridge_playtest.py --dir <ABSOLUTE run dir> --setup <setup.json> [--model NAME] [--port 8765]

The game runs unchanged with provider "openai". Its base URL points at a small
OpenAI-compatible server in this process. Each chat completion the game sends
(draft, verifier, repairs, quest parser, setup passes) is written to
``<dir>/calls/NNNN.request.json`` with a readable ``NNNN.view.txt``, and the
server waits until ``NNNN.reply.txt`` appears; its text is returned as the
model's answer. So whoever writes the replies is the model, and sees what a
cloud model sees.

Player turns arrive the same way: write ``<dir>/inbox/NNN.txt`` (the player's
line; ``STOP`` ends the run). After each turn ``<dir>/turns/NNN.json`` holds
what the engine did, and every 10 turns and at the end the world database is
exported with tools/export_world_db.py into ``<dir>/db/``.

``<dir>/status.txt`` says what the run is waiting for:
``call NNNN`` (a model reply), ``player NNN`` (the next line), ``done`` or ``error``.

All data paths are isolated inside ``<dir>/data`` (never the live data/).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# Packet keys that repeat every call and are not needed to answer it.
VIEW_DROP = {"settings", "setting_templates", "people_leaning", "active_skills", "world_epoch_label"}
VIEW_STR = 600
VIEW_LIST = 8


class Run:
    def __init__(self, run_dir: Path, model: str):
        self.dir = run_dir
        self.model = model
        self.calls = run_dir / "calls"
        self.inbox = run_dir / "inbox"
        self.turns = run_dir / "turns"
        self.db_out = run_dir / "db"
        for d in (self.calls, self.inbox, self.turns, self.db_out):
            d.mkdir(parents=True, exist_ok=True)
        self.seq = 0
        self.lock = threading.Lock()
        self.calls_this_turn: list[dict[str, Any]] = []

    def status(self, text: str) -> None:
        (self.dir / "status.txt").write_text(text + "\n", encoding="utf-8")

    # --- the model side -------------------------------------------------------
    def answer(self, body: dict[str, Any]) -> str:
        with self.lock:
            self.seq += 1
            n = self.seq
        tag = f"{n:04d}"
        (self.calls / f"{tag}.request.json").write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        (self.calls / f"{tag}.view.txt").write_text(self.view(body), encoding="utf-8")
        reply = self.calls / f"{tag}.reply.txt"
        self.status(f"call {tag}")
        started = time.time()
        while not reply.exists():
            time.sleep(0.25)
        time.sleep(0.2)  # let the writer finish
        text = reply.read_text(encoding="utf-8")
        self.calls_this_turn.append({"call": tag, "wait_s": round(time.time() - started, 1), "chars": len(text)})
        self.status("running")
        return text

    def view(self, body: dict[str, Any]) -> str:
        msgs = body.get("messages") or []
        system = next((m.get("content") for m in msgs if m.get("role") == "system"), "") or ""
        user = next((m.get("content") for m in msgs if m.get("role") == "user"), "") or ""
        digest = hashlib.sha1(system.encode("utf-8")).hexdigest()[:10]
        sys_file = self.calls / f"system_{digest}.txt"
        if not sys_file.exists():
            sys_file.write_text(system, encoding="utf-8")
        head = [
            f"max_tokens={body.get('max_tokens')} json={bool(body.get('response_format'))} temperature={body.get('temperature')}",
            f"system: system_{digest}.txt ({len(system)} chars) :: {system[:240]!r}",
            f"user: {len(user)} chars",
            "",
        ]
        return "\n".join(head) + _compact_user(user)


def _shrink(value: Any, depth: int = 0) -> Any:
    if isinstance(value, dict):
        return {k: _shrink(v, depth + 1) for k, v in value.items() if k not in VIEW_DROP}
    if isinstance(value, list):
        out = [_shrink(v, depth + 1) for v in value[:VIEW_LIST]]
        if len(value) > VIEW_LIST:
            out.append(f"... {len(value) - VIEW_LIST} more")
        return out
    if isinstance(value, str) and len(value) > VIEW_STR:
        return value[:VIEW_STR] + f" ...<{len(value)} chars>"
    return value


def _compact_user(user: str) -> str:
    start = user.find("{")
    if start < 0:
        return user
    try:
        packet, end = json.JSONDecoder().raw_decode(user[start:])
    except ValueError:
        return user
    before = user[:start].strip()
    after = user[start + end :].strip()
    body = json.dumps(_shrink(packet), ensure_ascii=False, indent=1)
    return "\n".join(p for p in (before, body, after) if p)


def serve(run: Run, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # quiet
            pass

        def _send(self, payload: dict[str, Any]) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            self._send({"object": "list", "data": [{"id": run.model, "object": "model"}]})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            text = run.answer(body)
            self._send(
                {
                    "id": "bridge",
                    "object": "chat.completion",
                    "model": run.model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                }
            )

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--setup", required=True, type=Path)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--resume", action="store_true", help="continue an existing run dir: no new game, numbering continues")
    ap.add_argument(
        "--local-model",
        default="",
        help="a GGUF path or MLE model name: that model is the GM through MLE and no bridge runs; "
        "player lines still come from the inbox",
    )
    ap.add_argument(
        "--viewer-port",
        type=int,
        default=0,
        help="also serve the game page on this port, read-only, following each new turn live "
        "(open http://127.0.0.1:<port>/ in a browser)",
    )
    args = ap.parse_args()
    run_dir = args.dir.resolve()
    run = Run(run_dir, args.model)
    if args.resume:
        run.seq = max([int(p.name[:4]) for p in run.calls.glob("[0-9][0-9][0-9][0-9].request.json")] or [0])

    from playtest_setup_presets import isolated_data_env

    env = isolated_data_env(str(run_dir / "data"))
    (run_dir / "data" / "source_index").mkdir(parents=True, exist_ok=True)
    (run_dir / "data" / "model_traces").mkdir(parents=True, exist_ok=True)
    os.environ.update(env)
    # Keep every turn's trace, not only the newest 50.
    os.environ["AI_RPG_MODEL_TRACE_KEEP"] = "400"
    base = f"http://127.0.0.1:{args.port}/v1"
    local = str(args.local_model or "").strip()
    if local:
        os.environ.update(
            {
                "AI_RPG_MODEL_PROVIDER": "mle",
                "MLE_MODEL": local,
                "AI_RPG_MLE_TIMEOUT": "900",
                "AI_RPG_TURN_DRAFT_TIMEOUT": "900",
                "AI_RPG_TURN_VERIFY_TIMEOUT": "600",
            }
        )
    else:
        os.environ.update(
            {
                "AI_RPG_MODEL_PROVIDER": "openai",
                "AI_RPG_API_BASE_URL": base,
                "AI_RPG_API_MODEL": args.model,
                "AI_RPG_API_KEY": "bridge",
                # The model is a person at a keyboard: wait for it.
                **{
                    name: "7200"
                    for name in (
                        "AI_RPG_TURN_DRAFT_TIMEOUT", "AI_RPG_TURN_VERIFY_TIMEOUT", "AI_RPG_QUEST_PARSER_TIMEOUT",
                        "AI_RPG_JSON_REPAIR_TIMEOUT", "AI_RPG_SETUP_COHERENCE_TIMEOUT", "AI_RPG_SETUP_RANDOMIZER_TIMEOUT",
                        "AI_RPG_SUGGESTION_TIMEOUT", "AI_RPG_AMBIENT_TIMEOUT", "AI_RPG_LLAMA_CPP_TIMEOUT", "AI_RPG_MLE_TIMEOUT",
                    )
                },
            }
        )
        serve(run, args.port)

    if args.viewer_port:
        # Same process, same isolated save: the page only reads (MORKYN_SPECTATE).
        os.environ["MORKYN_SPECTATE"] = "1"
        import uvicorn

        viewer = uvicorn.Server(
            uvicorn.Config("app.main:app", host="127.0.0.1", port=args.viewer_port, log_level="warning")
        )
        viewer.install_signal_handlers = lambda: None
        threading.Thread(target=viewer.run, daemon=True).start()
        print(f"Watch live: http://127.0.0.1:{args.viewer_port}/", flush=True)

    from app import turn_ledger
    from app.db import connect, init_db
    from app.llm import update_model_config
    from app.world import get_state, play_turn, play_wait_turn, start_playthrough_with_opening
    from export_world_db import export, markdown

    def export_db(label: str) -> None:
        data = export(Path(env["AI_RPG_DB"]))
        (run.db_out / f"{label}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        (run.db_out / f"{label}.md").write_text(markdown(data, label), encoding="utf-8")

    def snapshot() -> dict[str, Any]:
        with connect().closing() as conn:
            p = conn.execute("SELECT name, level, xp, gold, health, max_health, energy, current_location_id FROM player").fetchone()
            loc = conn.execute("SELECT name FROM locations WHERE id = ?", (p["current_location_id"],)).fetchone() if p else None
            return {
                "player": dict(p) if p else {},
                "location": loc["name"] if loc else "",
                "inventory": [f"{r['name']} x{r['quantity']}" for r in conn.execute("SELECT name, quantity FROM inventory WHERE quantity > 0")],
                "max_journal": conn.execute("SELECT COALESCE(MAX(id), 0) FROM journal").fetchone()[0],
                "max_dice": conn.execute("SELECT COALESCE(MAX(id), 0) FROM dice_rolls").fetchone()[0],
            }

    def turn_record(n: int, line: str, result: Any, before: dict[str, Any], seconds: float) -> dict[str, Any]:
        after = snapshot()
        with connect().closing() as conn:
            journal = [dict(r) for r in conn.execute("SELECT turn, kind, content FROM journal WHERE id > ?", (before["max_journal"],))]
            dice = [dict(r) for r in conn.execute(
                "SELECT tag, kind, band, notation, value, source FROM dice_rolls WHERE id > ?", (before["max_dice"],))]
        res = result if isinstance(result, dict) else {}
        # The engine ledger of this turn (app/turn_ledger.py): what changed and which code changed it.
        ledger = turn_ledger.last_finished() or {}
        engine = {
            "delta": ledger.get("delta"),
            "notes": ledger.get("notes") or [],
            "write_count": len(ledger.get("writes") or []),
            "trace": ((res.get("debug") or {}).get("trace_name") if isinstance(res.get("debug"), dict) else "") or "",
        }
        return {
            "engine": engine,
            "turn": n,
            "player_line": line,
            "seconds": round(seconds, 2),
            "model_calls": list(run.calls_this_turn),
            "used_fallback": bool(res.get("used_fallback")),
            "fallback_reason": res.get("fallback_reason") or "",
            "narration": next((j["content"] for j in journal if j["kind"] == "narration"), ""),
            "engine_journal": [j for j in journal if j["kind"] not in {"narration", "player"}],
            "dice": dice,
            "before": {k: v for k, v in before.items() if not k.startswith("max_")},
            "after": {k: v for k, v in after.items() if not k.startswith("max_")},
        }

    try:
        run.status("running setup")
        init_db()
        if local:
            update_model_config({"provider": "mle", "mle_model": local})
        else:
            update_model_config({"provider": "openai", "api_base_url": base, "api_model": args.model, "api_key": "bridge"})
        n = 0
        if args.resume:
            n = max([int(p.stem) for p in run.turns.glob("[0-9][0-9][0-9].json")] or [0])
        else:
            setup = json.loads(args.setup.read_text(encoding="utf-8"))
            before = {"player": {}, "location": "", "inventory": [], "max_journal": 0, "max_dice": 0}
            run.calls_this_turn = []
            t0 = time.time()
            opening = start_playthrough_with_opening(setup)
            record = turn_record(0, "(opening)", opening, before, time.time() - t0)
            (run.turns / "000.json").write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            export_db("turn-000")
        while True:
            n += 1
            box = run.inbox / f"{n:03d}.txt"
            run.status(f"player {n:03d}")
            while not box.exists():
                time.sleep(0.25)
            time.sleep(0.2)
            line = box.read_text(encoding="utf-8").strip()
            if line == "STOP":
                break
            run.status("running")
            run.calls_this_turn = []
            before = snapshot()
            turn_ledger.clear_last()
            t0 = time.time()
            try:
                if line.startswith("!wait"):
                    # The Wait / Meditate / Sleep buttons (POST /api/wait): "!wait <minutes> <kind>".
                    parts = line.split()
                    minutes = int(parts[1]) if len(parts) > 1 else 60
                    kind = parts[2] if len(parts) > 2 else "wait"
                    result = play_wait_turn(minutes, kind=kind)
                else:
                    result = play_turn(line)
            except Exception as exc:  # a turn that raises is a finding, not the end of the run
                result = {"used_fallback": True, "fallback_reason": f"EXCEPTION {type(exc).__name__}: {exc}"[:400],
                          "traceback": traceback.format_exc()[-2000:]}
            record = turn_record(n, line, result, before, time.time() - t0)
            if isinstance(result, dict) and result.get("traceback"):
                record["traceback"] = result["traceback"]
            (run.turns / f"{n:03d}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            if n % 10 == 0:
                export_db(f"turn-{n:03d}")
        export_db("final")
        state = get_state(include_hidden=True)
        (run.dir / "final_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1, default=str)[:2_000_000], encoding="utf-8")
        run.status("done")
        return 0
    except Exception:
        (run.dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        run.status("error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
