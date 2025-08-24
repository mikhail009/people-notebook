from __future__ import annotations

from datetime import date
from typing import Optional
from urllib.parse import quote_plus


def calc_age(d: Optional[int], m: Optional[int], y: Optional[int]) -> Optional[int]:
    if not (d and m and y):
        return None
    try:
        today = date.today()
        bd = date(y, m, d)
        age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        return age
    except Exception:
        return None


def compose_address(city: Optional[str], address: Optional[str], apartment: Optional[str]) -> Optional[str]:
    parts = [p.strip() for p in [city, address] if p and p.strip()]
    if apartment and str(apartment).strip():
        parts.append(f"кв. {apartment}".strip())
    if not parts:
        return None
    return ", ".join(parts)


def yandex_maps_url(address_str: str) -> str:
    # Простая ссылока поиска по адресу
    q = quote_plus(address_str)
    return f"https://yandex.ru/maps/?text={q}"
