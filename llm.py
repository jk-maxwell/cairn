"""
Cairn shared generation client: one place that speaks both chat dialects.

config.GEN_DIALECT selects the wire format; everything else about calling the
generation model (URL, model name, timeout) also comes from config.py /
models.local.json. Callers (ask.py, enrich.py, interview.py) never see the
dialect -- they call chat() with plain messages and get text back, streamed or
not.

Dialects:
  ollama  -- POST {GEN_CHAT_URL} (.../api/chat), JSON body, response is either
             a single JSON object (stream=False) or newline-delimited JSON
             objects, each with message.content, terminated by one with
             done=true.
  openai  -- POST {GEN_CHAT_URL} (.../v1/chat/completions), JSON body, response
             is either a single JSON object (stream=False) or an SSE stream of
             "data: {...}" lines, each choices[0].delta.content, terminated by
             a literal "data: [DONE]" line.

Security/contract requirements this module exists to enforce, not just
document (see the LaaS remote-endpoint constraints in the build task):
  - No Authorization header is ever sent. Auth is disabled server-side; a 401
    means server drift, not a missing key -- surface it, do not invent one.
  - TLS verification is never disabled. urllib.request verifies by default
    (ssl.create_default_context()); this module does not touch that.
  - temperature=0 is sent EXPLICITLY on every call, in both dialects. The
    remote server's default sampling is temperature 1.0; Cairn requires
    greedy, deterministic decoding for evidence-grounded answering.
  - Cairn's pipeline is already sequential (one call in flight at a time);
    this module does not add concurrency, matching a server that serializes
    requests anyway.

stdlib only: urllib.request/error, json. No new dependencies.
"""

import json
import urllib.error
import urllib.request

import config


class LLMError(RuntimeError):
    """A generation call failed in a way the caller should see, not swallow."""


def _timeout(timeout):
    return timeout if timeout is not None else config.GEN_TIMEOUT_S


def _headers():
    # Deliberately no Authorization header -- auth is disabled on the remote
    # endpoint by design. Do not add one, even if a call ever 401s: that is
    # server drift to report, not a signal to start sending credentials.
    return {"Content-Type": "application/json"}


# ---- Ollama dialect ----------------------------------------------------------

def _ollama_payload(messages, stream, temperature, max_tokens):
    payload = {
        "model": config.GEN_MODEL,
        "messages": messages,
        "stream": stream,
        "think": False,
        "options": {"temperature": temperature},
    }
    if max_tokens is not None:
        payload["options"]["num_predict"] = max_tokens
    return payload


def _ollama_chat(messages, stream, temperature, max_tokens, timeout):
    payload = json.dumps(_ollama_payload(messages, stream, temperature, max_tokens)).encode("utf-8")
    req = urllib.request.Request(config.GEN_CHAT_URL, data=payload, headers=_headers())

    if not stream:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("message", {}).get("content", "")

    def gen():
        # Errors are caught and re-raised as LLMError HERE, inside the
        # generator body, because a generator function's own code does not
        # run until first iterated -- a try/except around the call that
        # RETURNS this generator would never see a urlopen failure.
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for line in resp:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line.decode("utf-8"))
                    piece = obj.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if obj.get("done"):
                        break
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            raise LLMError(f"ollama streaming chat call to {config.GEN_CHAT_URL} failed: "
                            f"{type(e).__name__}: {e}") from e
    return gen()


# ---- OpenAI dialect -----------------------------------------------------------

def _openai_payload(messages, stream, temperature, max_tokens):
    payload = {
        "model": config.GEN_MODEL,
        "messages": messages,
        "stream": stream,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    return payload


def _openai_chat(messages, stream, temperature, max_tokens, timeout):
    payload = json.dumps(_openai_payload(messages, stream, temperature, max_tokens)).encode("utf-8")
    req = urllib.request.Request(config.GEN_CHAT_URL, data=payload, headers=_headers())

    if not stream:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choices = data.get("choices") or []
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""

    def gen():
        # SSE: unbuffered, "data: {...}" lines, terminated by a literal
        # "data: [DONE]" line. Never cut this stream off early -- prompt
        # ingestion on the remote edge can take well over a minute before the
        # first token, and the caller's timeout (not this loop) is what should
        # end a call that is genuinely stuck.
        #
        # Errors are caught and re-raised as LLMError HERE, inside the
        # generator body -- see the matching comment in _ollama_chat's gen().
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    obj = json.loads(data_str)
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    piece = choices[0].get("delta", {}).get("content", "")
                    if piece:
                        yield piece
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            raise LLMError(f"openai streaming chat call to {config.GEN_CHAT_URL} failed: "
                            f"{type(e).__name__}: {e}") from e
    return gen()


# ---- public entry point -------------------------------------------------------

def chat(messages, *, stream=False, temperature=0.0, max_tokens=None, timeout=None):
    """
    Call the configured generation model. Dialect is config.GEN_DIALECT.

    messages    -- list of {"role": ..., "content": ...} dicts, OpenAI/Ollama
                   shared shape.
    stream      -- False: returns the full response text as a str.
                   True: returns an iterator of text pieces (str).
    temperature -- MUST be passed explicitly by grounded callers; default 0.0
                   here matches Cairn's requirement to always decode greedily,
                   but callers should not rely on the default -- pass it.
    max_tokens  -- caps generated tokens (Ollama: num_predict, OpenAI: max_tokens).
                   None means "let the server decide" (no cap sent).
    timeout     -- seconds; defaults to config.GEN_TIMEOUT_S, which must budget
                   for queue wait + prompt ingestion on a shared/remote edge,
                   not just decode time.

    Raises LLMError on transport failure (the caller decides how to degrade --
    e.g. enrich.py logs a warning and skips enrichment for one document rather
    than crashing the whole ingest run).
    """
    t = _timeout(timeout)
    try:
        if config.GEN_DIALECT == "openai":
            return _openai_chat(messages, stream, temperature, max_tokens, t)
        return _ollama_chat(messages, stream, temperature, max_tokens, t)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise LLMError(f"{config.GEN_DIALECT} chat call to {config.GEN_CHAT_URL} failed: "
                        f"{type(e).__name__}: {e}") from e
