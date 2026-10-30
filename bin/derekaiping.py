"""Derek+ AI provider call, run from the search head.

Streaming search command (chunked protocol v2, standard library only). Each input
row supplies provider, model, endpoint, api_key, ai_brief, and is_ping. The
command calls the provider over HTTPS and adds ai_result, ai_reply, ai_error,
and ai_http. It drops api_key from the output so the key never reaches results.

The key comes from the saved KV Store row on the search that invokes this command.
It is never written to a file, logged, or placed in the search string.

Anthropic uses the Messages API with x-api-key. OpenAI, Cisco, and custom
OpenAI-compatible endpoints use a Bearer token. Azure OpenAI uses api-key.
"""
import csv
import io
import ipaddress
import json
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_DEFAULT_MODEL = "claude-haiku-5-5"
RETIRED_MODEL_RE = re.compile(r"^(claude-opus-4$|claude-3-)")
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "gpt-4o-mini"
PING_PROMPT = "Reply with the single word PONG. Do not request secrets."
SYSTEM_PROMPT = (
    "You are Derek+ Health Agent. Diagnose Splunk ingestion and infrastructure health. "
    "Do not request secrets. Do not claim you applied a Splunk change. "
    "Reply with likely cause, confidence, and admin steps."
)
KEY_RE = re.compile(r"^[A-Za-z0-9._/=+-]{8,512}$")
ADDED_FIELDS = ["ai_result", "ai_reply", "ai_error", "ai_http"]
PING_TIMEOUT = 20
ASK_TIMEOUT = 60
MAX_REPLY = 4000


class ProviderError(Exception):
    def __init__(self, message, http_status=""):
        super().__init__(message)
        self.http_status = str(http_status or "")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects, so the key header cannot be sent to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def tls_context():
    ctx = ssl.create_default_context()
    if hasattr(ssl, "TLSVersion"):
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def check_endpoint(url):
    parsed = urllib.parse.urlparse(url or "")
    if parsed.scheme != "https" or not parsed.hostname:
        raise ProviderError("Endpoint must be an https URL")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise ProviderError("Cannot resolve " + parsed.hostname)
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if addr.is_loopback or addr.is_link_local or addr.is_unspecified or addr.is_multicast:
            raise ProviderError("Endpoint resolves to a blocked address")


def anthropic_endpoint(endpoint):
    url = (endpoint or "").strip()
    if url and url != "none" and "anthropic.com" in url.lower():
        return url.replace("/v1/models", "/v1/messages") if url.rstrip("/").endswith("/v1/models") else url
    return ANTHROPIC_MESSAGES_URL


def anthropic_model(model):
    name = (model or "").strip()
    if name and name != "none" and name.lower().startswith("claude") and not RETIRED_MODEL_RE.match(name.lower()):
        return name
    return ANTHROPIC_DEFAULT_MODEL


def build_request(provider, endpoint, key, model, prompt, is_ping):
    max_tokens = 16 if is_ping else 1024
    user_prompt = PING_PROMPT if is_ping else prompt
    if provider == "anthropic":
        url = anthropic_endpoint(endpoint)
        body = {
            "model": anthropic_model(model),
            "max_tokens": max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
        return url, body, headers
    name = model if model and model != "none" else DEFAULT_MODEL
    body = {
        "model": name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    if provider == "azure":
        headers["api-key"] = key
    else:
        headers["Authorization"] = "Bearer " + key
    return (endpoint or "").strip(), body, headers


def extract_reply(provider, payload):
    if provider == "anthropic":
        parts = [b.get("text", "") for b in payload.get("content", []) if isinstance(b, dict)]
        return "".join(parts).strip()
    return str(payload["choices"][0]["message"]["content"]).strip()


def error_text(exc):
    detail = ""
    try:
        raw = exc.read().decode("utf-8", "replace")
        payload = json.loads(raw)
        err = payload.get("error", payload) if isinstance(payload, dict) else {}
        detail = err.get("message", "") if isinstance(err, dict) else str(err)
    except (OSError, ValueError, AttributeError):
        detail = ""
    if exc.code in (401, 403):
        base = "Provider rejected the API key (HTTP %d)" % exc.code
    elif exc.code == 404:
        base = "Provider returned HTTP 404; check the model name and endpoint"
    elif exc.code == 429:
        base = "Provider rate limit or quota reached (HTTP 429)"
    else:
        base = "Provider returned HTTP %d" % exc.code
    return (base + ". " + detail).strip()


def call_provider(provider, endpoint, key, model, prompt, is_ping):
    url, body, headers = build_request(provider, endpoint, key, model, prompt, is_ping)
    check_endpoint(url)
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=tls_context()))
    timeout = PING_TIMEOUT if is_ping else ASK_TIMEOUT
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = resp.status
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderError(error_text(exc), exc.code)
    except urllib.error.URLError as exc:
        raise ProviderError("Cannot reach provider: " + str(exc.reason))
    except (TimeoutError, socket.timeout):
        raise ProviderError("Provider timed out after %d seconds" % timeout)
    except ValueError:
        raise ProviderError("Provider returned a response that is not JSON")
    try:
        reply = extract_reply(provider, payload)
    except (KeyError, IndexError, TypeError):
        raise ProviderError("Provider response had no reply text", status)
    if not reply:
        raise ProviderError("Provider returned an empty reply", status)
    return reply, status


def clean_error(message, key):
    text = str(message)
    if key:
        text = text.replace(key, "***")
    text = re.sub(r"[^A-Za-z0-9 .:_/,()'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:300]


def process_row(row):
    provider = (row.get("provider") or "").strip().lower()
    key = (row.get("api_key") or "").strip()
    model = (row.get("model") or "").strip()
    endpoint = (row.get("endpoint") or "").strip()
    prompt = row.get("ai_brief") or ""
    is_ping = (row.get("is_ping") or "").strip() == "1"
    result = {"ai_result": "failed", "ai_reply": "", "ai_error": "", "ai_http": ""}
    try:
        if provider not in ("anthropic", "openai", "cisco", "azure", "custom"):
            raise ProviderError("No provider is set")
        if not KEY_RE.match(key):
            raise ProviderError("API key is missing or malformed. Enter the key and click SAVE")
        reply, status = call_provider(provider, endpoint, key, model, prompt, is_ping)
        result.update(ai_result="replied", ai_reply=reply[:MAX_REPLY], ai_http=str(status))
    except ProviderError as exc:
        result.update(ai_error=clean_error(exc, key), ai_http=exc.http_status)
    except Exception as exc:  # noqa: BLE001 - never crash the search; report a clean failure
        result.update(ai_error=clean_error("Unexpected error: %s" % type(exc).__name__, key))
    return result


def transform(body_text):
    reader = csv.DictReader(io.StringIO(body_text))
    in_fields = [f for f in (reader.fieldnames or []) if f != "api_key"]
    out_fields = in_fields + [f for f in ADDED_FIELDS if f not in in_fields]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=out_fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in reader:
        merged = dict(row)
        merged.update(process_row(row))
        writer.writerow(merged)
    return out.getvalue() if reader.fieldnames else ""


def read_chunk(stream):
    header = stream.readline()
    if not header:
        return None
    match = re.match(r"^chunked 1\.0,(\d+),(\d+)\s*$", header.decode("utf-8", "replace"))
    if not match:
        raise ValueError("Bad chunked header")
    meta_len, body_len = int(match.group(1)), int(match.group(2))
    meta = json.loads(stream.read(meta_len).decode("utf-8") or "{}")
    body = stream.read(body_len).decode("utf-8") if body_len else ""
    return meta, body


def write_chunk(stream, meta, body=""):
    meta_bytes = json.dumps(meta).encode("utf-8")
    body_bytes = body.encode("utf-8")
    stream.write(("chunked 1.0,%d,%d\n" % (len(meta_bytes), len(body_bytes))).encode("utf-8"))
    stream.write(meta_bytes)
    stream.write(body_bytes)
    stream.flush()


def main():
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    while True:
        chunk = read_chunk(stdin)
        if chunk is None:
            return 0
        meta, body = chunk
        if meta.get("action") == "getinfo":
            write_chunk(stdout, {"type": "streaming", "generating": False})
            continue
        try:
            out_body = transform(body) if body.strip() else ""
            write_chunk(stdout, {"finished": bool(meta.get("finished"))}, out_body)
        except Exception as exc:  # noqa: BLE001
            write_chunk(stdout, {"finished": True, "error": "derekaiping failed: %s" % type(exc).__name__})
            return 1
        if meta.get("finished"):
            return 0


if __name__ == "__main__":
    sys.exit(main())
