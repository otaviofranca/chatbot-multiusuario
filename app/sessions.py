"""Gestão de sessões em memória (histórico efêmero, isolado por sessão)."""
import asyncio
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Session:
    id: str
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    # Cada item: {"role": "user" | "model", "text": str}
    history: list[dict] = field(default_factory=list)
    # Lock por sessão: evita duas mensagens da MESMA sessão misturarem o histórico.
    # Sessões diferentes não se bloqueiam entre si (concorrência real).
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.last_active = time.time()


class SessionStore:
    def __init__(self, ttl_seconds: int = 1800, max_history: int = 20):
        self._sessions: dict[str, Session] = {}
        self.ttl = ttl_seconds
        self.max_history = max_history  # nº máximo de mensagens mantidas por sessão

    def create(self) -> Session:
        session = Session(id=uuid.uuid4().hex)
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        if session:
            session.touch()
        return session

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def trim(self, session: Session) -> None:
        if len(session.history) > self.max_history:
            session.history = session.history[-self.max_history:]

    def cleanup_expired(self) -> int:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now - s.last_active > self.ttl]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def __len__(self) -> int:
        return len(self._sessions)
