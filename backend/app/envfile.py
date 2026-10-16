""".env support without extra dependencies.

Precedence: real process environment > .env file > config/llm.yaml defaults.
The file is re-read on every lookup, so flipping a flag in .env applies on the next
validation run without restarting the server.
"""

from __future__ import annotations

import os
from pathlib import Path


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


class Env:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, key: str, default: str | None = None) -> str | None:
        if os.environ.get(key):
            return os.environ[key]
        return read_env_file(self.path).get(key) or default
