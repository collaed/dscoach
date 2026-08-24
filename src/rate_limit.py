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
    """Remove expired entries for an IP (caller holds lock)."""
    if ip in _attempts:
        cutoff = now - WINDOW_SECONDS
        _attempts[ip] = [t for t in _attempts[ip] if t > cutoff]
        if not _attempts[ip]:
            del _attempts[ip]


def is_rate_limited(ip: str) -> bool:
    """Check if an IP has exceeded the login attempt limit."""
    now = time.time()
    with _lock:
        _cleanup_ip(ip, now)
        attempts = _attempts.get(ip, [])
        return len(attempts) >= MAX_ATTEMPTS


def record_failed_attempt(ip: str) -> None:
    """Record a failed login attempt for an IP."""
    now = time.time()
    with _lock:
        _cleanup_ip(ip, now)
        if ip not in _attempts:
            _attempts[ip] = []
        _attempts[ip].append(now)


def reset_attempts(ip: str) -> None:
    """Clear failed attempts for an IP (on successful login)."""
    with _lock:
        _attempts.pop(ip, None)


def remaining_attempts(ip: str) -> int:
    """Return how many attempts remain before rate limiting kicks in."""
    now = time.time()
    with _lock:
        _cleanup_ip(ip, now)
        used = len(_attempts.get(ip, []))
        return max(0, MAX_ATTEMPTS - used)
