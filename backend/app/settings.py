"""Filesystem locations. Every path can be overridden by environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _path(env: str, default: Path) -> Path:
    value = os.environ.get(env)
    return Path(value).resolve() if value else default


@dataclass(frozen=True)
class Settings:
    rules_path: Path
    llm_config_path: Path
    personas_path: Path
    scenarios_dir: Path
    runtime_dir: Path
    frontend_dist: Path
    env_path: Path = REPO_ROOT / ".env"

    @property
    def audit_path(self) -> Path:
        return self.runtime_dir / "audit.jsonl"

    @property
    def runs_dir(self) -> Path:
        return self.runtime_dir / "runs"


def load_settings() -> Settings:
    return Settings(
        rules_path=_path("ACH_RULES_PATH", REPO_ROOT / "config" / "rules" / "ach_db_next_day.yaml"),
        llm_config_path=_path("ACH_LLM_CONFIG_PATH", REPO_ROOT / "config" / "llm.yaml"),
        personas_path=_path("ACH_PERSONAS_PATH", REPO_ROOT / "config" / "personas.yaml"),
        scenarios_dir=_path("ACH_SCENARIOS_DIR", REPO_ROOT / "data" / "scenarios"),
        runtime_dir=_path("ACH_RUNTIME_DIR", REPO_ROOT / "runtime"),
        frontend_dist=_path("ACH_FRONTEND_DIST", REPO_ROOT / "frontend" / "dist"),
        env_path=_path("ACH_ENV_FILE", REPO_ROOT / ".env"),
    )
