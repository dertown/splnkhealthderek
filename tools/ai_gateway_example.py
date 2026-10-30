#!/usr/bin/env python3
"""Example webhook receiver for Derek+ provider mode. Not shipped in the Cloud .spl.

Secrets come from the environment only. Never put API keys or HEC tokens in the app.

  export OPENAI_API_KEY=...          # or CISCO_API_KEY / AZURE_OPENAI_API_KEY / ANTHROPIC_API_KEY
  export SPLUNK_HEC_URL=https://http-inputs.example.splunkcloud.com/services/collector
  export SPLUNK_HEC_TOKEN=...
  python3 tools/ai_gateway_example.py

Point the Splunk webhook action on **Exec Health - AI provider dispatch** at
http://127.0.0.1:8787/webhook (or your TLS terminator). Override exec_health_ai_inbox
to the index/sourcetype this script sends (default sourcetype=derek_health_ai).
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN = os.environ.get("DEREK_AI_LISTEN", "127.0.0.1:8787")
HEC_URL = os.environ.get("SPLUNK_HEC_URL", "")
HEC_TOKEN = os.environ.get("SPLUNK_HEC_TOKEN", "")
HEC_SOURCETYPE = os.environ.get("DEREK_AI_SOURCETYPE", "derek_health_ai")
HEC_INDEX = os.environ.get("DEREK_AI_INDEX", "")
DEFAULT_MODEL = os.environ.get("DEREK_AI_DEFAULT_MODEL", "gpt-4o-mini")


def env_key(provider: str) -> str:
    names = {
        "openai": "OPENAI_API_KEY",
        "cisco": "CISCO_API_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "custom": "CUSTOM_AI_API_KEY",
    }
    var = names.get(provider, "OPENAI_API_KEY")
    return os.environ.get(var) or os.environ.get("OPENAI_API_KEY") or ""


def chat_openai_compatible(
    endpoint: str, key: str, model: str, prompt: str, azure: bool, timeout: int = 60
) -> str:
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Derek+ Health Agent. Diagnose Splunk ingestion and infrastructure "
                    "health. Do not request secrets. Do not claim you applied a Splunk change. "
                    "Reply with likely cause, confidence, and admin steps."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    if timeout <= 20:
        body["max_tokens"] = 16
    headers = {"Content-Type": "application/json"}
    if azure:
        headers["api-key"] = key
    else:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def chat_anthropic(endpoint: str, key: str, model: str, prompt: str, timeout: int = 60) -> str:
    body = {
        "model": model,
        "max_tokens": 16 if timeout <= 20 else 1024,
        "system": (
            "You are Derek+ Health Agent. Diagnose Splunk health. Do not request secrets. "
            "Do not claim you applied a Splunk change."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["content"][0]["text"]


def hec_send(event: dict) -> None:
    if not HEC_URL or not HEC_TOKEN:
        raise RuntimeError("SPLUNK_HEC_URL and SPLUNK_HEC_TOKEN must be set")
    envelope = {"event": event, "sourcetype": HEC_SOURCETYPE}
    if HEC_INDEX:
        envelope["index"] = HEC_INDEX
    req = urllib.request.Request(
        HEC_URL,
        data=json.dumps(envelope).encode("utf-8"),
        headers={"Authorization": "Splunk " + HEC_TOKEN, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as resp:
        resp.read()


def payload_key(result: dict, provider: str) -> str:
    """Prefer the key saved on AI provider setup; fall back to the environment."""
    saved = (result.get("api_key") or "").strip()
    if saved and saved != "none":
        return saved
    return env_key(provider)


def handle_result(result: dict) -> dict:
    provider = (result.get("provider") or "openai").strip().lower()
    endpoint = (result.get("endpoint") or "").strip()
    model = (result.get("model") or "").strip()
    note = (result.get("note") or "").strip()
    finding_id = result.get("finding_id")
    is_ping = note == "connection_test" or finding_id == "connection_test"
    timeout = 20 if is_ping else 60
    if not model or model == "none":
        model = DEFAULT_MODEL
    prompt = result.get("ai_brief") or result.get("issue") or ""
    key = payload_key(result, provider)
    try:
        if not key:
            raise RuntimeError("No API key saved or in the environment for provider " + provider)
        if not endpoint or endpoint == "none":
            raise RuntimeError("No endpoint configured for provider " + provider)
        if provider == "anthropic":
            reply = chat_anthropic(endpoint, key, model, prompt, timeout=timeout)
        else:
            reply = chat_openai_compatible(
                endpoint, key, model, prompt, azure=(provider == "azure"), timeout=timeout
            )
        event = {
            "finding_id": finding_id,
            "entity": result.get("entity"),
            "issue": result.get("issue"),
            "provider": provider,
            "model": model,
            "reply": reply,
            "status": "replied",
            "note": note or "ask_ai_provider",
            "conn_status": "PASS" if is_ping else "",
        }
        hec_send(event)
        return {"ok": True, "finding_id": event["finding_id"]}
    except (urllib.error.URLError, RuntimeError, KeyError, IndexError, TimeoutError) as exc:
        if is_ping:
            fail_event = {
                "finding_id": finding_id or "connection_test",
                "entity": result.get("entity") or "ai_setup",
                "issue": "connection_test",
                "provider": provider,
                "model": model,
                "reply": str(exc)[:200],
                "status": "failed",
                "note": "connection_test",
                "conn_status": "FAIL",
            }
            hec_send(fail_event)
            return {"ok": False, "finding_id": fail_event["finding_id"], "error": str(exc)[:200]}
        raise


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _write(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/webhook":
            self._write(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._write(400, {"ok": False, "error": "invalid json"})
            return
        results = []
        if isinstance(payload.get("result"), dict):
            results.append(payload["result"])
        if isinstance(payload.get("results"), list):
            results.extend([row for row in payload["results"] if isinstance(row, dict)])
        if not results:
            self._write(400, {"ok": False, "error": "no results"})
            return
        try:
            replies = [handle_result(row) for row in results]
        except (urllib.error.URLError, RuntimeError, KeyError, IndexError) as exc:
            self._write(502, {"ok": False, "error": str(exc)})
            return
        self._write(200, {"ok": True, "replies": replies})


def main() -> int:
    host, port_s = LISTEN.rsplit(":", 1)
    if not HEC_URL or not HEC_TOKEN:
        print("Set SPLUNK_HEC_URL and SPLUNK_HEC_TOKEN before listening", file=sys.stderr)
        return 1
    server = ThreadingHTTPServer((host, int(port_s)), Handler)
    print(f"Derek+ AI gateway example listening on http://{host}:{port_s}/webhook")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
