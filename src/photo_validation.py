"""LLM-based photo proof validation for task submissions.

Architecture:
- Coach enables photo validation globally (stored in coach.features JSON)
- Coach sets a per-coachee validation percentage (coachee.features.photo_validation_pct)
- Task templates can have photo_validate=1 to require validation on that task
- On task submission with photo, the system decides (based on pct) whether to run AI validation
- AI returns a confidence score (0-100) and assessment text
- Coach can always override the AI decision

Services supported:
- cloudflare: Uses Cloudflare Workers AI (existing _cf_ai_complete infra)
- openai: Uses OpenAI Vision API (requires API key)

The validation result is stored as JSON in task_assignment.photo_validation_result:
{
    "status": "validated" | "rejected" | "uncertain",
    "confidence": 0-100,
    "assessment": "free text explanation",
    "service": "cloudflare" | "openai",
    "validated_at": "ISO datetime"
}

Coach override stored in task_assignment.photo_validation_override:
{
    "decision": "approve" | "reject",
    "comment": "free text",
    "by": "coach"
}
"""

import base64
import json
import random
from datetime import datetime

from helpers import db, utcnow


def _get_coach_photo_settings(coach_id):
    """PURPOSE: Read the coach's photo-validation settings from coach.features JSON; None if disabled.
    CALLED BY / SCREEN: should_validate_photo() and validate_photo_proof() in this module — backs
    coachee task-submission validation (/me tasks) driven by coach settings.
    WHEN: on a coachee task submission with a photo, before deciding/running validation."""
    c = db()
    c.execute("SELECT features FROM coach WHERE id=%s", (coach_id,))
    row = c.fetchone()
    if not row or not row["features"]:
        return None
    features = json.loads(row["features"]) if isinstance(row["features"], str) else row["features"]
    pv = features.get("photo_validation")
    if not pv or not pv.get("enabled"):
        return None
    return pv


def _get_coachee_validation_pct(coachee_id):
    """PURPOSE: Return the coachee's photo-validation percentage (0-100) from coachee.features
    (defaults 100).
    CALLED BY / SCREEN: should_validate_photo() in this module — governs the /me task-submission
    validation roll.
    WHEN: on a coachee photo task submission, during the validation-decision roll."""
    c = db()
    c.execute("SELECT features FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    if not row or not row["features"]:
        return 100  # Default: validate all if enabled
    features = json.loads(row["features"]) if isinstance(row["features"], str) else (row["features"] or {})
    return features.get("photo_validation_pct", 100)


def should_validate_photo(coach_id, coachee_id, template_id):
    """PURPOSE: Decide whether to run AI validation for this submission (coach enabled + template
    photo_validate + random roll vs coachee percentage).
    CALLED BY / SCREEN: routes_coachee.py task-submit handler (POST /me task submission) — coachee
    tasks screen.
    WHEN: on coachee submitting a photo-proof task (form submit).

    Returns True if:
    1. Coach has photo validation enabled
    2. The task template has photo_validate=1
    3. Random roll passes the coachee's validation percentage
    """
    settings = _get_coach_photo_settings(coach_id)
    if not settings:
        return False

    # Check if template requires photo validation
    c = db()
    c.execute("SELECT photo_validate FROM task_template WHERE id=%s", (template_id,))
    tmpl = c.fetchone()
    if not tmpl or not tmpl.get("photo_validate"):
        return False

    # Roll against coachee percentage
    pct = _get_coachee_validation_pct(coachee_id)
    if pct <= 0:
        return False
    if pct >= 100:
        return True
    return random.randint(1, 100) <= pct


def validate_photo_proof(task_assignment_id, attachment_path, task_title, task_description, coach_id):
    """PURPOSE: Run AI validation on a submitted photo proof (read/encode image, call the configured
    LLM service, store the result JSON on the task_assignment). Returns result dict or None.
    CALLED BY / SCREEN: routes_coachee.py task-submit handler (POST /me task submission), after
    should_validate_photo() passes — coachee tasks screen; result later shown on coach grading screen.
    WHEN: on coachee photo-task submission when validation is triggered."""
    settings = _get_coach_photo_settings(coach_id)
    if not settings:
        return None

    service = settings.get("service", "cloudflare")

    # Read image and encode
    try:
        with open(attachment_path, "rb") as f:
            img_data = f.read()
        img_b64 = base64.b64encode(img_data).decode()
    except (FileNotFoundError, IOError):
        return None

    # Build prompt
    prompt = _build_validation_prompt(task_title, task_description)

    # Call the appropriate service
    if service == "openai":
        result = _validate_with_openai(img_b64, prompt, settings.get("api_key", ""))
    else:
        # Default: cloudflare (text-only analysis since CF doesn't support vision natively)
        result = _validate_with_cloudflare(img_b64, prompt)

    if result:
        result["service"] = service
        result["validated_at"] = utcnow().isoformat()
        # Store result
        c = db()
        c.execute(
            "UPDATE task_assignment SET photo_validation_result=%s WHERE id=%s",
            (json.dumps(result), task_assignment_id),
        )

    return result


def _build_validation_prompt(task_title, task_description):
    """PURPOSE: Build the LLM prompt (with strict JSON output spec) for photo-proof validation.
    CALLED BY / SCREEN: validate_photo_proof() in this module — feeds the coachee task-submission
    validation flow (/me tasks).
    WHEN: during photo validation, on coachee task submission."""
    desc_part = f"\nTask description: {task_description}" if task_description else ""
    return f"""You are a coaching assistant validating photo proof submissions. 
A coachee submitted a photo as proof of completing a task.

Task title: {task_title}{desc_part}

Analyze the photo and determine:
1. Does the photo appear to show genuine completion of this task?
2. Is the photo recent (not obviously old/recycled)?
3. Is there any indication of fraud or stock imagery?

Respond in this exact JSON format:
{{"status": "validated" or "rejected" or "uncertain", "confidence": 0-100, "assessment": "brief explanation (max 100 words)"}}

Be fair but vigilant. When uncertain, prefer "uncertain" over "rejected"."""


def _validate_with_cloudflare(img_b64, prompt):
    """PURPOSE: Perform a text-based (no native vision) validation via Cloudflare Workers AI and
    parse a status/confidence/assessment JSON; falls back to "uncertain".
    CALLED BY / SCREEN: validate_photo_proof() when service == cloudflare (default) — coachee
    task-submission validation (/me tasks).
    WHEN: during photo validation on coachee task submission when CF service is configured.

    Note: CF Workers AI llama models don't natively support vision.
    We describe what we expect and ask for a text-based assessment.
    For actual image analysis, OpenAI Vision is preferred.
    """
    from ai import _cf_ai_complete

    # Since CF doesn't support vision, we do a simplified text-based check
    simplified_prompt = prompt.replace("Analyze the photo and determine:", "Based on the task requirements, assess whether a photo submission is likely valid:")
    simplified_prompt += "\n\nNote: You cannot see the actual image. Based on the task nature, provide a general assessment of what valid proof would look like and mark as 'uncertain' since visual verification is needed."

    response = _cf_ai_complete(simplified_prompt, max_tokens=300)
    if response.startswith("[AI"):
        return None

    # Try to parse JSON from response
    try:
        # Find JSON in response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(response[start:end])
            # Validate structure
            if "status" in result and "confidence" in result:
                result["confidence"] = max(0, min(100, int(result["confidence"])))
                if result["status"] not in ("validated", "rejected", "uncertain"):
                    result["status"] = "uncertain"
                return result
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    # Fallback: uncertain
    return {"status": "uncertain", "confidence": 30, "assessment": "Could not perform visual analysis. Coach review recommended."}


def _validate_with_openai(img_b64, prompt, api_key):
    """PURPOSE: Validate the photo via OpenAI Vision (gpt-4o-mini), parsing a status/confidence/
    assessment JSON; returns "uncertain" on missing key or error.
    CALLED BY / SCREEN: validate_photo_proof() when the coach's service == openai — coachee
    task-submission validation (/me tasks).
    WHEN: during photo validation on coachee task submission when OpenAI service is configured."""
    if not api_key:
        return {"status": "uncertain", "confidence": 0, "assessment": "OpenAI API key not configured."}

    import urllib.error
    import urllib.request

    url = "https://api.openai.com/v1/chat/completions"
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "low"}},
                ],
            }
        ],
        "max_tokens": 300,
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
            # Parse JSON from response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(content[start:end])
                result["confidence"] = max(0, min(100, int(result.get("confidence", 50))))
                if result.get("status") not in ("validated", "rejected", "uncertain"):
                    result["status"] = "uncertain"
                return result
    except urllib.error.HTTPError as e:
        e.read()  # consume response body
        return {"status": "uncertain", "confidence": 0, "assessment": f"OpenAI API error: HTTP {e.code}"}
    except Exception as e:
        return {"status": "uncertain", "confidence": 0, "assessment": f"Validation error: {str(e)[:100]}"}

    return {"status": "uncertain", "confidence": 30, "assessment": "Could not parse AI response."}


def get_validation_status(task_assignment_row):
    """PURPOSE: Resolve the effective photo-validation status for display, preferring a coach
    override over the AI result (else None).
    CALLED BY / SCREEN: display utility for the coach grade-submissions screen; not currently
    referenced elsewhere in src/ (no live caller found via grep).
    WHEN: intended for coach grading screen render, per submission with a photo proof.

    Priority: coach override > AI result > none
    Returns dict with keys: status, confidence, assessment, source, override
    """
    override_raw = task_assignment_row.get("photo_validation_override")
    result_raw = task_assignment_row.get("photo_validation_result")

    override = None
    if override_raw:
        try:
            override = json.loads(override_raw) if isinstance(override_raw, str) else override_raw
        except (json.JSONDecodeError, TypeError):
            pass

    result = None
    if result_raw:
        try:
            result = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
        except (json.JSONDecodeError, TypeError):
            pass

    if override:
        return {
            "status": "approved" if override.get("decision") == "approve" else "rejected",
            "confidence": 100,
            "assessment": override.get("comment", ""),
            "source": "coach",
            "override": override,
            "ai_result": result,
        }

    if result:
        return {
            "status": result.get("status", "uncertain"),
            "confidence": result.get("confidence", 0),
            "assessment": result.get("assessment", ""),
            "source": result.get("service", "ai"),
            "override": None,
            "ai_result": result,
        }

    return None
