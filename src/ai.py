"""AI integration: Cloudflare Workers AI, Hetzner Inference, and profile generation."""

import json
import os

from helpers import db

# Cloudflare Workers AI configuration
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")
CF_MODEL = os.environ.get("CF_MODEL", "@cf/meta/llama-3.1-8b-instruct")

# Hetzner Inference API configuration
HETZNER_API_KEY = os.environ.get("HETZNER_API_KEY", "")
HETZNER_BASE_URL = os.environ.get("HETZNER_BASE_URL", "https://inference.hetzner.com/api/v1")
HETZNER_MODEL = os.environ.get("HETZNER_MODEL", "Qwen/Qwen3.6-35B-A3B-FP8")

# AI backend selection: "hetzner" or "cloudflare" (default: hetzner if configured, else cloudflare)
AI_BACKEND = os.environ.get("AI_BACKEND", "hetzner" if HETZNER_API_KEY else "cloudflare")

MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY", "")
LLM_KEY = MISTRAL_KEY


def _hetzner_ai_complete(prompt, max_tokens=1024, system_prompt=None):
    """Call Hetzner Inference API (OpenAI-compatible). Returns response text or error string."""
    if not HETZNER_API_KEY:
        return "[AI not configured: HETZNER_API_KEY required]"
    import urllib.error
    import urllib.request

    url = f"{HETZNER_BASE_URL}/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": HETZNER_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Authorization": f"Bearer {HETZNER_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode())
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content")
                if content:
                    return content
                return "[AI error: empty response content]"
            return f"[AI error: no choices in response]"
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        if e.code == 429:
            return "[AI rate limited: retry in 60s]"
        return f"[AI HTTP {e.code}: {body}]"
    except Exception as e:
        return f"[AI error: {e}]"


def _cf_ai_complete(prompt, max_tokens=1024):
    """Call Cloudflare Workers AI REST API. Returns response text or error string."""
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        return "[AI not configured: CF_ACCOUNT_ID and CF_API_TOKEN required]"
    import urllib.error
    import urllib.request

    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_MODEL}"
    payload = json.dumps({"messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            if data.get("success"):
                return data.get("result", {}).get("response", "")
            return f"[AI error: {data.get('errors', 'unknown')}]"
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        return f"[AI HTTP {e.code}: {body}]"
    except Exception as e:
        return f"[AI error: {e}]"


def ai_complete(prompt, max_tokens=1024, system_prompt=None):
    """Unified AI completion: dispatches to configured backend.

    Falls back to the other backend on failure.
    """
    if AI_BACKEND == "hetzner":
        result = _hetzner_ai_complete(prompt, max_tokens=max_tokens, system_prompt=system_prompt)
        if result.startswith("[AI") and CF_ACCOUNT_ID and CF_API_TOKEN:
            # Fallback to Cloudflare
            return _cf_ai_complete(prompt, max_tokens=max_tokens)
        return result
    else:
        result = _cf_ai_complete(prompt, max_tokens=max_tokens)
        if result.startswith("[AI") and HETZNER_API_KEY:
            # Fallback to Hetzner
            return _hetzner_ai_complete(prompt, max_tokens=max_tokens, system_prompt=system_prompt)
        return result


def _build_profile_prompt(coachee_id):
    """Build the Mistral prompt from coachee history."""
    c = db()
    c.execute("SELECT name, context_text, coach_id FROM coachee WHERE id=%s", (coachee_id,))
    coachee_row = c.fetchone()
    if not coachee_row:
        return None
    name = coachee_row["name"]
    c.execute("SELECT name FROM coach WHERE id=%s", (coachee_row["coach_id"],))
    coach_name = c.fetchone()["name"]
    c.execute(
        "SELECT checkin_type, content, created_at FROM checkin WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 50",
        (coachee_id,),
    )
    checkins = c.fetchall()
    c.execute(
        """SELECT tt.title, ta.status, ta.response, ta.created_at FROM task_assignment ta
                 JOIN task_template tt ON ta.template_id=tt.id WHERE ta.coachee_id=%s ORDER BY ta.created_at DESC LIMIT 30""",
        (coachee_id,),
    )
    tasks = c.fetchall()
    c.execute(
        "SELECT category, content, created_at FROM tracking_log WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 30",
        (coachee_id,),
    )
    tracking = c.fetchall()
    c.execute(
        "SELECT author_role, content, created_at FROM note WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20",
        (coachee_id,),
    )
    notes = c.fetchall()
    c.execute(
        "SELECT ack_type, description FROM acknowledgement WHERE coachee_id=%s ORDER BY created_at DESC LIMIT 20",
        (coachee_id,),
    )
    acks = c.fetchall()

    def fmt(rows):
        return "\n".join(f"  [{r.get('created_at','')}] {dict(r)}" for r in rows) or "  (none)"

    prompt = f"""I am {coach_name}, a rather dominant coach, and I am talking to you about a person called {name} whom I am coaching. You are a coaching psychology assistant. Based on the following data for coachee "{name}", write a concise psychological profile (max 300 words) to help me understand them better. Cover: emotional patterns, discipline/consistency, areas of strength, areas needing attention, and overall trajectory. Be empathetic but honest. Use third person ("{name}" or "they").

CHECK-INS:
{fmt(checkins)}

TASKS (status & responses):
{fmt(tasks)}

TRACKING (food/hydration/exercise/emotional):
{fmt(tracking)}

NOTES (coach-coachee communication):
{fmt(notes)}

ACKNOWLEDGEMENTS:
{fmt(acks)}"""

    ctx = coachee_row.get("context_text") or ""
    if ctx:
        prompt += f"\n\nPAST EXCHANGES / ADDITIONAL CONTEXT:\n{ctx[:10000]}"
    return prompt
