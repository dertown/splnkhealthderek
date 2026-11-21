"""Derek+ AI provider call, run from the search head.

Streaming search command (chunked protocol v2, standard library plus Splunk's own
splunk.rest). Each input row supplies provider, model, endpoint, ai_brief, and
is_ping. The command calls the provider over HTTPS and adds ai_result, ai_reply,
ai_error, and ai_http. It drops any api_key field from the output.

The key is read from Splunk's credential store (storage/passwords, app
splunk_exec_health, realm splunk_exec_health_ai, user provider_api_key), where
bin/healthdash.py saved it, using the session key Splunk passes to this command.
Reading it needs the list_storage_passwords capability. The key is never written
to a file, logged, placed in the search string, or taken from search results.

Anthropic uses the Messages API with x-api-key. OpenAI, Cisco, and custom
OpenAI-compatible endpoints use a Bearer token. Azure OpenAI uses api-key.
An endpoint ending in /responses gets an OpenAI Responses API body; any other
non-Anthropic endpoint gets a chat completions body. Reasoning models (o-series,
gpt-5) get max_completion_tokens, a larger budget, and low reasoning effort.
Claude models that think by default (Claude 5, Fable) or take an effort setting
(Opus and Sonnet 4.6 and later) get the larger budget and output_config effort low.

An HTTP 200 with no answer text is reported with the provider's stop reason and
token use, and retried once with three times the budget when the budget ran out.
"""
import csv
import io
import ipaddress
import json
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

APP = "splunk_exec_health"
CRED_REALM = "splunk_exec_health_ai"
CRED_NAME = "provider_api_key"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_DEFAULT_MODEL = "claude-haiku-5-5"
RETIRED_MODEL_RE = re.compile(r"^(claude-opus-4$|claude-3-)")
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "gpt-4o-mini"
PING_PROMPT = "Reply with the single word PONG. Do not request secrets."
SYSTEM_PROMPT = (
    "You are Derek+ Health Agent. Diagnose Splunk ingestion and infrastructure health. "
    "Do not request secrets. Do not claim you applied a Splunk change. "
    "Reply in short sections, each starting with a bold heading such as **Root cause:**, "
    "**Confidence:** and **Admin steps:**. Follow any output format the user message asks for."
)
KEY_RE = re.compile(r"^[A-Za-z0-9._/=+-]{8,512}$")
ADDED_FIELDS = ["ai_result", "ai_reply", "ai_error", "ai_http"]
PING_TIMEOUT = 20
ASK_TIMEOUT = 60
MAX_REPLY = 6000
RETRY_STATUS = (429, 500, 502, 503, 504, 529)
RETRY_WAIT = 3
# Output token budgets. Reasoning models (OpenAI o-series and gpt-5) spend part of
# the budget on hidden reasoning before any answer text, so they get more room and
# use max_completion_tokens, which those models require instead of max_tokens.
ASK_TOKENS = 1400
PING_TOKENS = 16
REASONING_ASK_TOKENS = 6000
REASONING_PING_TOKENS = 512
MAX_TOKENS_CAP = 12000
REASONING_MODEL_RE = re.compile(r"^(o\d|gpt-5)", re.I)
# Claude models that take output_config.effort. Claude 5 models (Opus 5 and 5.5,
# Sonnet 5 and 5.5, Haiku 5.5) and Fable/Mythos think by default when the request
# leaves out thinking, and Sonnet 5.5 at high effort. Their thinking counts against
# max_tokens, so a small cap can return HTTP 200 with only thinking blocks. They get
# the reasoning budgets and low effort. Haiku 4.5 and older reject effort.
THINKING_CLAUDE_RE = re.compile(r"^claude-((fable|mythos)\b|(opus|sonnet|haiku)-(5\b|4-[6-9]\b))", re.I)
# Stop reasons that mean the output budget ran out.
BUDGET_STOPS = ("length", "max_tokens", "max_output_tokens", "incomplete")


class ProviderError(Exception):
    def __init__(self, message, http_status="", budget_hit=False):
        super().__init__(message)
        self.http_status = str(http_status or "")
        self.budget_hit = budget_hit


def is_reasoning_model(provider, model):
    """Models whose hidden reasoning counts against the output budget.

    OpenAI o-series and gpt-5 (including Azure deployments named after them), and
    Claude models that think by default or take an effort setting.
    """
    name = (model or "").strip().split("/")[-1]
    if provider == "anthropic":
        return bool(THINKING_CLAUDE_RE.match(name))
    return bool(REASONING_MODEL_RE.match(name))


def is_responses_api(url):
    return urllib.parse.urlparse(url or "").path.rstrip("/").endswith("/responses")


def token_budget(provider, model, is_ping, scale=1):
    if is_reasoning_model(provider, model):
        base = REASONING_PING_TOKENS if is_ping else REASONING_ASK_TOKENS
    else:
        base = PING_TOKENS if is_ping else ASK_TOKENS
    return min(base * scale, MAX_TOKENS_CAP)


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


def build_request(provider, endpoint, key, model, prompt, is_ping, scale=1):
    user_prompt = PING_PROMPT if is_ping else prompt
    if provider == "anthropic":
        url = anthropic_endpoint(endpoint)
        name = anthropic_model(model)
        body = {
            "model": name,
            "max_tokens": token_budget(provider, name, is_ping, scale),
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if is_reasoning_model(provider, name):
            # Thinking stays at the model's default (it cannot be turned off on
            # Opus 5.5 or Sonnet 5.5); low effort keeps it short for these answers.
            body["output_config"] = {"effort": "low"}
        headers = {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
        return url, body, headers
    name = model if model and model != "none" else DEFAULT_MODEL
    url = (endpoint or "").strip()
    budget = token_budget(provider, name, is_ping, scale)
    reasoning = is_reasoning_model(provider, name)
    if is_responses_api(url):
        body = {"model": name, "instructions": SYSTEM_PROMPT, "input": user_prompt,
                "max_output_tokens": budget}
        if reasoning:
            body["reasoning"] = {"effort": "low"}
    else:
        body = {
            "model": name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        if reasoning:
            # These models reject max_tokens and any temperature other than the default.
            body["max_completion_tokens"] = budget
            body["reasoning_effort"] = "low"
        else:
            body["max_tokens"] = budget
            body["temperature"] = 0.2
    headers = {"Content-Type": "application/json"}
    if provider == "azure":
        headers["api-key"] = key
    else:
        headers["Authorization"] = "Bearer " + key
    return url, body, headers


def _text(content):
    """Answer text from a string, a list of content parts, or None."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and part.get("type") in (None, "text", "output_text"):
                out.append(str(part.get("text") or ""))
        return "".join(out)
    return ""


def extract_reply(provider, payload):
    """Return (answer text, details) where details explain an empty answer.

    details holds stop (the provider's stop reason), refusal, reasoning (True when
    the model produced reasoning but no answer), used and reasoning_tokens.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload is not an object")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    info = {"stop": "", "refusal": "", "reasoning": False,
            "used": usage.get("output_tokens") or usage.get("completion_tokens") or "",
            "reasoning_tokens": ((usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {})
                                 .get("reasoning_tokens") or "")}
    if provider == "anthropic" and "content" in payload:
        blocks = [b for b in payload.get("content") or [] if isinstance(b, dict)]
        info["stop"] = str(payload.get("stop_reason") or "")
        info["reasoning"] = any(b.get("type") in ("thinking", "redacted_thinking") for b in blocks)
        text = "".join(str(b.get("text") or "") for b in blocks if b.get("type") in (None, "text"))
        return text.strip(), info
    if "choices" in payload:
        choice = payload["choices"][0]
        message = choice.get("message") or {}
        info["stop"] = str(choice.get("finish_reason") or "")
        info["refusal"] = str(message.get("refusal") or "")
        info["reasoning"] = bool(message.get("reasoning_content") or message.get("reasoning"))
        return _text(message.get("content")).strip(), info
    if "output" in payload or "output_text" in payload:
        # OpenAI Responses API.
        info["stop"] = str(payload.get("status") or "")
        details = payload.get("incomplete_details")
        if isinstance(details, dict) and details.get("reason"):
            info["stop"] = str(details["reason"])
        if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
            return payload["output_text"].strip(), info
        out = []
        for item in payload.get("output") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "reasoning":
                info["reasoning"] = True
            elif item.get("type") == "message":
                for part in item.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "refusal":
                        info["refusal"] = str(part.get("refusal") or "")
                out.append(_text(item.get("content")))
        return "".join(out).strip(), info
    raise KeyError("no choices, content, or output")


def empty_reason(info):
    """Explain an HTTP 200 with no answer text, using what the provider reported."""
    stop = info.get("stop") or "not given"
    used = info.get("used")
    tokens = ""
    if used:
        tokens = ", %s output tokens used" % used
        if info.get("reasoning_tokens"):
            tokens += ", %s of them on reasoning" % info["reasoning_tokens"]
    base = "Provider returned HTTP 200 with no answer text (stop reason %s%s)." % (stop, tokens)
    if info.get("refusal"):
        return base + " The model refused: " + info["refusal"]
    if stop in BUDGET_STOPS:
        return base + (" The model used its whole output budget before answering, even after one retry with a"
                       " larger budget. Choose a faster model, such as Claude Haiku or gpt-4o-mini.")
    if stop in ("content_filter", "refusal"):
        return base + " The provider's content filter or safety system blocked the answer."
    if info.get("reasoning"):
        return base + " The model returned only reasoning. The endpoint may need a reasoning parser, or the model is not a chat model."
    return base


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
    """Call the provider, with one retry.

    The retry happens when the provider is busy (429, 5xx), briefly unreachable, or
    answered 200 with no text because the output budget ran out; that retry gets
    three times the budget. Only one retry, so the search stays inside its timeout.
    """
    try:
        return call_once(provider, endpoint, key, model, prompt, is_ping)
    except ProviderError as exc:
        if exc.budget_hit:
            return call_once(provider, endpoint, key, model, prompt, is_ping, scale=3)
        busy = exc.http_status.isdigit() and int(exc.http_status) in RETRY_STATUS
        if is_ping or not (busy or str(exc).startswith("Cannot reach provider")):
            raise
    time.sleep(RETRY_WAIT)
    return call_once(provider, endpoint, key, model, prompt, is_ping)


def call_once(provider, endpoint, key, model, prompt, is_ping, scale=1):
    url, body, headers = build_request(provider, endpoint, key, model, prompt, is_ping, scale)
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
        reply, info = extract_reply(provider, payload)
    except (KeyError, IndexError, TypeError, AttributeError):
        keys = ", ".join(sorted(payload)[:8]) if isinstance(payload, dict) else type(payload).__name__
        raise ProviderError("Provider returned HTTP %s in a format this app does not read (top-level fields: %s)."
                            " The endpoint should be an OpenAI-compatible chat completions or responses URL."
                            % (status, keys), status)
    if not reply:
        budget_hit = info.get("stop") in BUDGET_STOPS and not info.get("refusal") and scale == 1
        raise ProviderError(empty_reason(info), status, budget_hit=budget_hit)
    return reply, status


def clean_error(message, key):
    text = str(message)
    if key:
        text = text.replace(key, "***")
    text = re.sub(r"[^A-Za-z0-9 .:_/,()'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:400]


NO_KEY = "API key is not in the credential store or is malformed. Enter the key and click SAVE"
NO_READ = ("This user cannot read the credential store (HTTP 403). Reading the key needs the"
           " list_storage_passwords capability and read access to this app's passwords")


def read_stored_key(session_key):
    """Return (key, problem) from storage/passwords. key is "" when it cannot be read.

    splunk.rest.simpleRequest raises for 404 and 403 even with raiseAllErrors=False;
    the exception's statusCode tells a missing key from a permission problem.
    """
    if not session_key:
        return "", "No session key was passed to the command"
    try:
        import splunk.rest as rest  # provided by Splunk's Python; not packaged
    except ImportError:
        return "", "splunk.rest is not available"
    entity = "/servicesNS/nobody/%s/storage/passwords/%s" % (
        APP, urllib.parse.quote("%s:%s:" % (CRED_REALM, CRED_NAME), safe=""))
    try:
        resp, content = rest.simpleRequest(entity, sessionKey=session_key,
                                           getargs={"output_mode": "json"}, raiseAllErrors=False)
        status = int(resp.status)
    except Exception as exc:  # noqa: BLE001 - splunk.RESTException carries statusCode
        status = getattr(exc, "statusCode", None)
        if not isinstance(status, int):
            return "", "Could not read the credential store (%s)" % type(exc).__name__
        content = b""
    if status == 403:
        return "", NO_READ
    if status != 200:
        return "", NO_KEY
    try:
        entries = json.loads(content).get("entry") or []
        key = str(entries[0]["content"].get("clear_password") or "").strip() if entries else ""
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        key = ""
    return key, ("" if key else NO_KEY)


class KeySource:
    """Reads the key once per search, on the first row that needs it."""

    def __init__(self):
        self.session_key = ""
        self._key = None
        self.problem = ""

    def get(self):
        if self._key is None:
            self._key, self.problem = read_stored_key(self.session_key)
        return self._key


KEYS = KeySource()


def process_row(row):
    provider = (row.get("provider") or "").strip().lower()
    model = (row.get("model") or "").strip()
    endpoint = (row.get("endpoint") or "").strip()
    prompt = row.get("ai_brief") or ""
    is_ping = (row.get("is_ping") or "").strip() == "1"
    result = {"ai_result": "failed", "ai_reply": "", "ai_error": "", "ai_http": ""}
    key = ""
    try:
        if provider not in ("anthropic", "openai", "cisco", "azure", "custom"):
            raise ProviderError("No provider is set")
        key = KEYS.get()
        if not KEY_RE.match(key):
            raise ProviderError(KEYS.problem or NO_KEY)
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
            KEYS.session_key = str((meta.get("searchinfo") or {}).get("session_key") or "")
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
