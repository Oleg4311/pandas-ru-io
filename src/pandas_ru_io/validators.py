"""Проверка российских реквизитов по контрольным цифрам: ИНН, СНИЛС, ОГРН, ОГРНИП, КПП, БИК, расчётный счёт.

Каждая функция принимает строку с пробелами и дефисами (как их печатают в документах) и возвращает `bool`;
парные функции `*_error` возвращают причину отказа по-русски или `None`, если реквизит верен.
Проверяется только арифметика и формат: существование организации или человека эти функции не доказывают.
"""

from __future__ import annotations

import re

__all__ = [
    "account_error",
    "bik_error",
    "inn_error",
    "is_account",
    "is_bik",
    "is_inn",
    "is_kpp",
    "is_ogrn",
    "is_ogrnip",
    "is_snils",
    "kpp_error",
    "ogrn_error",
    "ogrnip_error",
    "snils_error",
]

_SEP = re.compile(r"[\s\-   ]")

_INN10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_1 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_2 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _digits(value: object, name: str, *lengths: int) -> tuple[str | None, str | None]:
    """Оставляет цифры; возвращает (цифры, None) или (None, причина)."""
    if not isinstance(value, str):
        return None, f"{name}: ожидалась строка"
    s = _SEP.sub("", value)
    if not s:
        return None, f"{name}: пусто"
    if not s.isascii() or not s.isdigit():
        return None, f"{name}: допустимы только цифры"
    if lengths and len(s) not in lengths:
        want = " или ".join(str(n) for n in lengths)
        return None, f"{name}: нужно {want} цифр, а не {len(s)}"
    return s, None


def _check(digits: str, weights: tuple[int, ...]) -> int:
    return sum(int(d) * w for d, w in zip(digits, weights, strict=False)) % 11 % 10


def inn_error(value: object) -> str | None:
    """ИНН юридического лица (10 цифр) или физического (12 цифр)."""
    s, err = _digits(value, "ИНН", 10, 12)
    if s is None:
        return err
    if len(s) == 10:
        return None if _check(s[:9], _INN10) == int(s[9]) else "ИНН: неверная контрольная цифра"
    if _check(s[:10], _INN12_1) != int(s[10]) or _check(s[:11], _INN12_2) != int(s[11]):
        return "ИНН: неверная контрольная цифра"
    return None


def is_inn(value: object) -> bool:
    return inn_error(value) is None


def snils_error(value: object) -> str | None:
    """СНИЛС: 9 цифр номера и 2 контрольные («112-233-445 95»). Номера до 001-001-998 контрольным числом не защищены и принимаются по формату."""
    s, err = _digits(value, "СНИЛС", 11)
    if s is None:
        return err
    number = s[:9]
    if int(number) <= 1001998:
        return None  # номера до 001-001-998 контрольным числом не защищены: принимаются по формату
    total = sum(int(d) * w for d, w in zip(number, range(9, 0, -1), strict=True))
    control = total if total < 100 else (0 if total in (100, 101) else total % 101 % 100)
    return None if control == int(s[9:]) else "СНИЛС: неверная контрольная сумма"


def is_snils(value: object) -> bool:
    return snils_error(value) is None


def ogrn_error(value: object) -> str | None:
    """ОГРН юридического лица: 13 цифр, последняя равна остатку от деления первых 12 на 11."""
    s, err = _digits(value, "ОГРН", 13)
    if s is None:
        return err
    return None if int(s[:12]) % 11 % 10 == int(s[12]) else "ОГРН: неверная контрольная цифра"


def is_ogrn(value: object) -> bool:
    return ogrn_error(value) is None


def ogrnip_error(value: object) -> str | None:
    """ОГРНИП индивидуального предпринимателя: 15 цифр, последняя равна остатку от деления первых 14 на 13."""
    s, err = _digits(value, "ОГРНИП", 15)
    if s is None:
        return err
    return None if int(s[:14]) % 13 % 10 == int(s[14]) else "ОГРНИП: неверная контрольная цифра"


def is_ogrnip(value: object) -> bool:
    return ogrnip_error(value) is None


_KPP = re.compile(r"[0-9]{4}[0-9A-Z]{2}[0-9]{3}")


def kpp_error(value: object) -> str | None:
    """КПП: 9 знаков, пятый и шестой могут быть заглавными латинскими буквами."""
    if not isinstance(value, str):
        return "КПП: ожидалась строка"
    s = _SEP.sub("", value)
    if len(s) != 9:
        return f"КПП: нужно 9 знаков, а не {len(s)}"
    return None if _KPP.fullmatch(s) else "КПП: неверный формат"


def is_kpp(value: object) -> bool:
    return kpp_error(value) is None


def bik_error(value: object) -> str | None:
    """БИК: 9 цифр, начинается с 04 (Россия)."""
    s, err = _digits(value, "БИК", 9)
    if s is None:
        return err
    return None if s.startswith("04") else "БИК: российский БИК начинается с 04"


def is_bik(value: object) -> bool:
    return bik_error(value) is None


_ACCOUNT_WEIGHTS = ((7, 1, 3) * 8)[:23]


def account_error(account: object, bik: object) -> str | None:
    """Расчётный счёт (20 цифр) по БИК банка: проверяется контрольный ключ в девятой позиции счёта.

    Перед счётом приписываются три цифры БИК: 7-я, 8-я и 9-я; для корреспондентских счетов (начинаются с 301) и подразделений
    Банка России (БИК оканчивается на 000, 001 или 002) берутся «0» и 5-я, 6-я цифры БИК. Полученные 23 цифры умножаются на коэффициенты 7, 1, 3 по кругу,
    складываются младшие разряды произведений, и сумма должна делиться на 10.
    """
    a, err = _digits(account, "Счёт", 20)
    if a is None:
        return err
    b, err = _digits(bik, "БИК", 9)
    if b is None:
        return err
    prefix = "0" + b[4:6] if (a.startswith("301") or b[6:9] in ("000", "001", "002")) else b[6:9]
    total = sum((int(d) * w) % 10 for d, w in zip(prefix + a, _ACCOUNT_WEIGHTS, strict=True))
    return None if total % 10 == 0 else "Счёт: контрольный ключ не сходится с БИК"


def is_account(account: object, bik: object) -> bool:
    return account_error(account, bik) is None
