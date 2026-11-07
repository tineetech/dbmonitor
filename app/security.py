import hmac
import secrets
import threading
import time
from collections import deque
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

PASSWORD_HASHER = PasswordHasher()

SESSION_COOKIE = "dbmonitor_session"

_serializer = URLSafeTimedSerializer(settings.APP_SECRET_KEY, salt="db-monitor-session")


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, Argon2Error):
        return False


def create_session(uid: int, username: str, role: str) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(32)
    payload = {"uid": uid, "sub": username, "role": role, "csrf": csrf}
    token = _serializer.dumps(payload)
    return token, csrf


def create_anonymous_session() -> tuple[str, str]:
    csrf = secrets.token_urlsafe(32)
    payload = {"uid": 0, "sub": "anonymous", "role": "anon", "csrf": csrf}
    token = _serializer.dumps(payload)
    return token, csrf


def load_session(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=settings.SESSION_EXPIRE_MINUTES * 60)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or "uid" not in data or "csrf" not in data:
        return None
    return data


def csrf_valid(session: dict, candidate: Optional[str]) -> bool:
    expected = str(session.get("csrf", ""))
    if not candidate:
        return False
    return hmac.compare_digest(expected, str(candidate))


class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, hits: deque[float], now: float) -> None:
        while hits and now - hits[0] > self.window:
            hits.popleft()

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            self._prune(hits, now)
            return len(hits) < self.max_attempts

    def record_failure(self, key: str) -> None:
        now = time.time()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            self._prune(hits, now)
            hits.append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


login_rate_limiter = RateLimiter(max_attempts=5, window_seconds=300)
 