"""Explainability service: renders configured reason templates into checker-readable text."""

from __future__ import annotations

ABSENT = "<absent>"
BLANK = "<blank>"


def show(value: str | None) -> str:
    if value is None:
        return ABSENT
    if value.strip() == "":
        return BLANK
    return value


class _Context(dict):
    def __missing__(self, key: str) -> str:  # placeholders are validated at config load
        return "{" + key + "}"


def render(template: str, **values: object) -> str:
    return template.format_map(_Context({k: "" if v is None else str(v) for k, v in values.items()}))
