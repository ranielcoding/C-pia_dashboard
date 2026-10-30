from __future__ import annotations

import math


def format_brl(value: object, decimals: int = 2) -> str:
    """Format a number as Brazilian reais without relying on host locale."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if not math.isfinite(number):
        number = 0.0
    formatted = f"{number:,.{decimals}f}"
    formatted = formatted.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return f"R$ {formatted}"


def format_pt_number(value: object, decimals: int = 0) -> str:
    """Format a number with Brazilian decimal and thousands separators."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if not math.isfinite(number):
        number = 0.0
    formatted = f"{number:,.{decimals}f}"
    return formatted.replace(",", "\0").replace(".", ",").replace("\0", ".")
