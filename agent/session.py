"""Persistent, append-only chat sessions stored as JSONL under .agent-cache."""

import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

SESSIONS_DIR = Path(".agent-cache") / "sessions"

Role = Literal["user", "assistant", "error"]


def uuid7() -> uuid.UUID:
    """Generates a time-ordered UUID version 7 (RFC 9562).

    Layout: 48-bit unix millisecond timestamp, 4-bit version (7), 12 random bits,
    2-bit variant (0b10), 62 random bits.
    """
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = (rand >> 62) & 0xFFF
    rand_b = rand & ((1 << 62) - 1)
    value = (
        ((unix_ms & ((1 << 48) - 1)) << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return uuid.UUID(int=value)


class SessionMessage(BaseModel):
    """One persisted message in a session."""

    role: Role = Field(
        ..., description="Who sent the message, or 'error' for a failed step."
    )
    content: str = Field(..., description="The message text.")
    model: str = Field(..., description="The model used for this exchange.")
    timestamp: str = Field(..., description="UTC ISO 8601 timestamp.")


class Session:
    """A chat session backed by an append-only JSONL file."""

    def __init__(self, session_id: str, path: Path):
        self.session_id = session_id
        self.path = path

    @classmethod
    def create(cls, root: Path = SESSIONS_DIR) -> "Session":
        """Creates a new session with a fresh uuid7 id."""
        root.mkdir(parents=True, exist_ok=True)
        session_id = str(uuid7())
        path = root / f"{session_id}.jsonl"
        path.touch()
        return cls(session_id, path)

    @classmethod
    def load(cls, session_id: str, root: Path = SESSIONS_DIR) -> "Session":
        """Loads an existing session. Raises ValueError or FileNotFoundError."""
        normalized = str(uuid.UUID(session_id))
        path = root / f"{normalized}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"Session not found: {session_id}")
        return cls(normalized, path)

    def messages(self) -> list[SessionMessage]:
        """Returns all saved messages in order."""
        return [
            SessionMessage.model_validate_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def append(self, role: Role, content: str, model: str) -> None:
        """Appends one message and flushes it to disk immediately."""
        message = SessionMessage(
            role=role,
            content=content,
            model=model,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(message.model_dump_json() + "\n")
            f.flush()
