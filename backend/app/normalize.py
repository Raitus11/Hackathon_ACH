"""Value normalizers named in the field dictionary of the rule configuration."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def _decimal(value: str) -> str:
    cleaned = value.replace(",", "").replace("$", "").strip()
    try:
        return format(Decimal(cleaned).normalize(), "f")
    except InvalidOperation:
        return value


_NORMALIZERS = {
    "trim": lambda v: v.strip(),
    "casefold": lambda v: v.casefold(),
    "upper": lambda v: v.upper(),
    "digits_only": lambda v: "".join(ch for ch in v if ch.isdigit()),
    "decimal": _decimal,
    "sorted_csv": lambda v: ",".join(sorted(p.strip().upper() for p in v.split(",") if p.strip())),
}


def normalize(value: str | None, steps: list[str]) -> str | None:
    if value is None:
        return None
    result = value
    for step in steps:
        result = _NORMALIZERS[step](result)
    return result


def is_blank(value: str | None) -> bool:
    return value is None or value.strip() == ""
