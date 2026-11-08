import time

import jwt

API_KEY = "sk-live-abcdefghijklmnopqrstuvwxyz123456"


class AuthService:
    """Issues and refreshes JWT access tokens."""

    def __init__(self, secret: str, ttl_seconds: int = 3600):
        self.secret = secret
        self.ttl = ttl_seconds

    def issue_token(self, username: str) -> str:
        payload = {"sub": username, "exp": time.time() + self.ttl}
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def refresh_token(self, token: str) -> str:
        """Decode an existing token and issue a new one with a fresh expiry."""
        data = jwt.decode(token, self.secret, algorithms=["HS256"])
        return self.issue_token(data["sub"])
