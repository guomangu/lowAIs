"""Minimal Agent Client Protocol (ACP) stdio server exposing StructuredAI Local in Zed."""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from structuredai.config_loader import build_config
from structuredai.steering import append_steering_directive, set_steering_status


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _send_chunk(session_id: str, text: str) -> None:
    upd = {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}
    _send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session_id, "update": upd}})


def _query_local_llm(cfg, prompt: str, dash_txt: str) -> str:
    url = cfg.llm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg.llm_model, "stream": False, "temperature": cfg.llm_temperature, "max_tokens": 512,
        "messages": [
            {"role": "system", "content": f"Assistant local StructuredAI. Contexte projet:\n{dash_txt[:1200]}"},
            {"role": "user", "content": prompt[:2000]},
        ],
    }
    if cfg.llm_disable_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=cfg.llm_timeout_sec) as r:
            body = json.loads(r.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"] or "(réponse vide)"
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
        return f"Serveur IA local ({url}) indisponible : {exc}\nLancez la tâche Zed 'StructuredAI: Demarrer / Reprendre (start.sh)' ou './start.sh'."


def handle_prompt(cfg, text: str) -> str:
    """Execute steering slash commands or forward question to local llama-server."""
    sdir = cfg.target_dir / cfg.state_dir_name
    dash_p, steer_p = sdir / "DASHBOARD.md", sdir / "STEERING.md"
    cmd = text.strip()
    if cmd == "/status":
        return dash_p.read_text(encoding="utf-8") if dash_p.is_file() else f"Aucun DASHBOARD.md actif dans {sdir}. Lancez './start.sh'."
    if cmd in {"/pause", "/resume", "/stop"}:
        st = {"/pause": "PAUSE", "/resume": "RUN", "/stop": "STOP"}[cmd]
        set_steering_status(steer_p, st)
        return f"STEERING.md mis à jour -> STATUS: {st}"
    if cmd.startswith(("/priority ", "/retry ")):
        verb, rel = cmd[1:].split(" ", 1)
        append_steering_directive(steer_p, verb.upper(), rel.strip())
        return f"STEERING.md mis à jour -> {verb.upper()}: {rel.strip()}"
    if cmd == "/help":
        return "Commandes : /status, /pause, /resume, /stop, /priority <fichier>, /retry <fichier>, ou posez une question au modèle local."
    dash_txt = dash_p.read_text(encoding="utf-8") if dash_p.is_file() else ""
    return _query_local_llm(cfg, cmd, dash_txt)


def handle_rpc(msg: dict, cfg) -> None:
    """Process one ACP JSON-RPC 2.0 request."""
    req_id, method, params = msg.get("id"), msg.get("method", ""), msg.get("params", {})
    if method == "initialize":
        caps = {"loadSession": False, "promptCapabilities": {"image": False, "audio": False, "embeddedContext": True}}
        info = {"name": "structuredai-local", "title": "StructuredAI Local", "version": "0.1.0"}
        _send({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": 1, "agentCapabilities": caps, "agentInfo": info, "authMethods": []}})
    elif method == "session/new":
        _send({"jsonrpc": "2.0", "id": req_id, "result": {"sessionId": "sai-local-1"}})
    elif method == "session/prompt":
        sid = params.get("sessionId", "sai-local-1")
        parts = [p.get("text", "") for p in params.get("prompt", []) if isinstance(p, dict) and p.get("type") == "text"]
        reply = handle_prompt(cfg, "\n".join(parts))
        _send_chunk(sid, reply)
        _send({"jsonrpc": "2.0", "id": req_id, "result": {"stopReason": "end_turn"}})
    elif req_id is not None:
        _send({"jsonrpc": "2.0", "id": req_id, "result": {}})


def main() -> int:
    cfg = build_config(Path(os.environ.get("STRUCTURED_AI_ENV", ".env")))
    for line in sys.stdin:
        if s := line.strip():
            handle_rpc(json.loads(s), cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
