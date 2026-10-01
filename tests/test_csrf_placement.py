"""Regression test for BUG-018 / H10: `{{ csrf_field() }}` must render INSIDE
its `<form>` element.

A CSRF hidden input placed after `</form>` is not submitted with the form, so
with server-side CSRF enforcement the POST is rejected (403). This silently
broke several one-line delete/toggle forms — including the coachee safe-word /
emergency-stop buttons, which the project charter treats as an absolute,
ungated circuit breaker.

This test is intentionally generic: it scans EVERY template and checks EVERY
occurrence of `csrf_field`, so it stays valid as new templates are added
(closing the bug class, not just the known instances).
"""

import os
import re

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "templates")

# Match <form ...> ... </form> spans (non-greedy, dotall for multiline forms).
_FORM_SPAN = re.compile(r"<form\b[^>]*>.*?</form>", re.DOTALL | re.IGNORECASE)
_CSRF = "csrf_field"


def _template_files():
    for name in os.listdir(TEMPLATES_DIR):
        if name.endswith(".html"):
            yield os.path.join(TEMPLATES_DIR, name)


def test_every_csrf_field_is_inside_a_form():
    offenders = []
    for path in _template_files():
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        if _CSRF not in html:
            continue
        form_ranges = [(m.start(), m.end()) for m in _FORM_SPAN.finditer(html)]
        for occ in re.finditer(_CSRF, html):
            pos = occ.start()
            if not any(lo <= pos < hi for lo, hi in form_ranges):
                # Report line number for a helpful failure message.
                line = html.count("\n", 0, pos) + 1
                offenders.append(f"{os.path.basename(path)}:{line}")
    assert not offenders, "csrf_field() rendered OUTSIDE a <form> (token won't be submitted → 403): " + ", ".join(
        offenders
    )


def test_safeword_forms_carry_csrf():
    """The safe-word / pause forms specifically must each contain csrf_field."""
    path = os.path.join(TEMPLATES_DIR, "coachee_dashboard.html")
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    pause_forms = [m.group(0) for m in _FORM_SPAN.finditer(html) if 'action="/me/pause"' in m.group(0)]
    assert pause_forms, "expected at least one /me/pause form in coachee dashboard"
    for form in pause_forms:
        assert _CSRF in form, "safe-word/pause form is missing csrf_field() inside the <form>"
