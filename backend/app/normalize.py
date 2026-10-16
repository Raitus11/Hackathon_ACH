"""Value normalizers named in the field dictionary of the rule configuration."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def _decimal(value: str) -> str:
    cleaned = value.replace(",", "").replace("$", "").strip()
    try:
        return format(Decimal(cleaned).normalize(), "f")
    except InvalidOperation:
        return value


def _aba_routing(value: str) -> str:
    """ABA routing numbers are 9 digits; spreadsheet exports drop the leading zero."""
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits.zfill(9) if digits else ""


def _yes_no(value: str) -> str:
    v = value.strip().upper()
    if v in {"Y", "YES", "1", "TRUE", "T"}:
        return "Y"
    if v in {"N", "NO", "0", "FALSE", "F", ""}:
        return "N"
    return v


_NORMALIZERS = {
    "trim": lambda v: v.strip(),
    "casefold": lambda v: v.casefold(),
    "upper": lambda v: v.upper(),
    "digits_only": lambda v: "".join(ch for ch in v if ch.isdigit()),
    "decimal": _decimal,
    "sorted_csv": lambda v: ",".join(sorted(p.strip().upper() for p in v.split(",") if p.strip())),
    "aba_routing": _aba_routing,
    "yes_no": _yes_no,
}


def normalize(value: str | None, steps: list[str], codes: dict[str, str] | None = None) -> str | None:
    """Apply the field's code map (source system code -> label) first, then each step in order."""
    if value is None:
        return None
    result = value
    if codes:
        result = codes.get(result.strip(), result)
    for step in steps:
        result = _NORMALIZERS[step](result)
    return result


def is_blank(value: str | None) -> bool:
    return value is None or value.strip() == ""
