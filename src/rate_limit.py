"""In-memory rate limiting for DSCoaching — stdlib only.

Simple sliding-window counter per IP. Sufficient for a single-process app with 2 users.
For multi-worker deployments, replace with a PG table or Redis.
"""

import time
import threading

# Config
MAX_ATTEMPTS = 5        # Max failed login attempts per window
WINDOW_SECONDS = 900    # 15 minutes

# Storage: {ip: [(timestamp, ...), ...]}
_attempts: dict[str, list[float]] = {}
_lock = threading.Lock()


def _cleanup_ip(ip: str, now: float) -> None:
    """PURPOSE: Drop attempt timestamps older than the sliding window for an IP (caller holds lock).
    CALLED BY / SCREEN: is_rate_limited(), record_failed_attempt(), remaining_attempts() here; no screen.
    WHEN: on each rate-limit check/record, i.e. during login POST handling."""
    if ip in _attempts:
        cutoff = now - WINDOW_SECONDS
        _attempts[ip] = [t for t in _attempts[ip] if t > cutoff]
        if not _attempts[ip]:
            del _attempts[ip]


def is_rate_limited(ip: str) -> bool:
    """PURPOSE: Return True if an IP has reached MAX_ATTEMPTS failed logins within the window.
    CALLED BY / SCREEN: auth.py login handler (GET/POST /login) — gates the public login screen.
    WHEN: at the start of each login POST attempt."""
    now = time.time()
    with _lock:
        _cleanup_ip(ip, now)
        attempts = _attempts.get(ip, [])
        return len(attempts) >= MAX_ATTEMPTS


def record_failed_attempt(ip: str) -> None:
    """PURPOSE: Append a failed-login timestamp for an IP to the sliding window.
    CALLED BY / SCREEN: auth.py login handler (/login) when credentials are wrong — login screen.
    WHEN: on each failed login POST."""
    now = time.time()
    with _lock:
        _cleanup_ip(ip, now)
        if ip not in _attempts:
            _attempts[ip] = []
        _attempts[ip].append(now)


def reset_attempts(ip: str) -> None:
    """PURPOSE: Clear an IP's failed-attempt history.
    CALLED BY / SCREEN: auth.py login handler (/login) on successful coach/coachee login — login screen.
    WHEN: immediately after a successful authentication."""
    with _lock:
        _attempts.pop(ip, None)


def remaining_attempts(ip: str) -> int:
    """PURPOSE: Return how many login attempts remain before rate limiting triggers.
    CALLED BY / SCREEN: available to auth.py/login screen for surfacing remaining tries (utility).
    WHEN: on demand during login flow / attempt-count display."""
    now = time.time()
    with _lock:
        _cleanup_ip(ip, now)
        used = len(_attempts.get(ip, []))
        return max(0, MAX_ATTEMPTS - used)
