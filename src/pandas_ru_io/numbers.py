"""Числа в русской записи: «1 234,56», «(1 000,00)», «12,5 руб.», «1.234,56», «−5,5»."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import pandas as pd

from .report import ParseReport

__all__ = ["format_number", "parse_number", "parse_numbers", "to_number"]

_SPACES = "       "
_MINUS = "-−–—‒"
_EMPTY = {"", "-", "—", "–", "н/д", "нд", "n/a", "na", "nan", "none", "null", "нет"}
_CURRENCY_PRE = re.compile(r"(?i)^(?:₽|руб(?:\.|лей|ля|ль)?|р\.|rub|rur)\s*")
_CURRENCY = re.compile(r"(?i)(?:₽|руб(?:\.|лей|ля|ль)?|р\.|rub|rur)\s*$")
_GROUPS = re.compile(r"\d{1,3}(?:[,.]\d{3})+")


def _clean(raw: Any) -> tuple[str | None, bool]:
    """Снимает пробелы, валюту, скобки и знак. Возвращает (цифры и разделители или None, отрицательное ли)."""
    if raw is None:
        return None, False
    if isinstance(raw, float) and raw != raw:
        return None, False
    s = str(raw).strip()
    if s.lower() in _EMPTY:
        return None, False
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    s = _CURRENCY_PRE.sub("", _CURRENCY.sub("", s)).strip()
    s = s.removesuffix("%").strip()
    if s and s[0] in _MINUS:
        negative = True
        s = s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()
    integer = re.split(r"[,.]", s)[0]
    if any(ch in integer for ch in _SPACES) and not re.fullmatch(rf"\d{{1,3}}(?:[{re.escape(_SPACES)}]\d{{3}})+", integer):
        return "!", negative  # пробелы внутри числа допустимы только как разделители тысяч: «1 2 3» это не число
    for ch in _SPACES:
        s = s.replace(ch, "")
    return s, negative


def _parse(raw: Any, decimal: str | None) -> tuple[Decimal | None, str]:
    """Возвращает (число, статус): 'ok', 'ambiguous', 'failed', 'empty'."""
    s, negative = _clean(raw)
    if s is None:
        return None, "empty"
    if not s or not re.fullmatch(r"[0-9.,]+", s) or not any(c.isdigit() for c in s):
        return None, "failed"
    if s[-1] in ",." and s.count(s[-1]) == 1:
        s = s[:-1]  # «5,» читается как 5
    if not s or (not s[0].isdigit() and not (s[0] in ",." and s.count(s[0]) == 1 and s[1:].isdigit())):
        return None, "failed"
    if s[0] in ",.":
        s = "0" + s  # «,5» читается как 0,5
    commas, dots = s.count(","), s.count(".")
    ambiguous = False
    if commas and dots:
        # последний разделитель — десятичный, другой — тысячи
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        if decimal is not None and dec != decimal:
            return None, "failed"
        int_part, _, frac = s.rpartition(dec)
        if s.count(dec) != 1 or not re.fullmatch(rf"\d{{1,3}}(?:{re.escape(thou)}\d{{3}})*", int_part) or not frac.isdigit():
            return None, "failed"
        number = int_part.replace(thou, "") + "." + frac
    elif commas or dots:
        sep = "," if commas else "."
        count = commas or dots
        head, _, tail = s.rpartition(sep)
        if decimal is None:
            # по умолчанию, как в русских таблицах, разделитель дробной части — запятая; точка тоже читается как десятичная
            if count == 1:
                number = f"{head}.{tail}" if head else f"0.{tail}"
                ambiguous = len(tail) == 3 and 1 <= len(head) <= 3
            elif re.fullmatch(rf"\d{{1,3}}(?:{re.escape(sep)}\d{{3}})+", s):
                number = s.replace(sep, "")  # 1,234,567 или 1.234.567: только тысячи
            else:
                return None, "failed"
        elif sep == decimal:
            if count != 1:
                return None, "failed"
            number = f"{head}.{tail}" if head else f"0.{tail}"
        else:
            # этот разделитель — тысячи
            if not re.fullmatch(rf"\d{{1,3}}(?:{re.escape(sep)}\d{{3}})+", s):
                return None, "failed"
            number = s.replace(sep, "")
    else:
        number = s
    try:
        value = Decimal(number)
    except InvalidOperation:
        return None, "failed"
    return (-value if negative else value), ("ambiguous" if ambiguous else "ok")


def parse_number(raw: Any, *, decimal: Literal[",", "."] | None = None) -> Decimal | None:
    """Разбирает одно число; `None` для пустого значения и для того, что числом не является.

    `decimal` — десятичный разделитель столбца: если он известен, «1,234» читается однозначно.
    Без него запятая и точка читаются как десятичные, а «1.234,56» и «1,234.56» — по последнему разделителю.
    """
    return _parse(raw, decimal)[0]


def parse_numbers(
    values: pd.Series[Any] | list[Any],
    *,
    decimal: Literal[",", "."] | None = None,
    as_decimal: bool = False,
) -> tuple[pd.Series[Any], ParseReport]:
    """Разбирает столбец чисел и возвращает (числа, отчёт).

    Десятичный разделитель столбца определяется по однозначным значениям («1 234,56» говорит о запятой, «1,234.56» о точке);
    если встречаются оба, это записывается в `report.notes['mixed']`. «1,234» без других подсказок остаётся
    в `report.ambiguous`. Непонятные значения превращаются в пропуск и попадают в `report.failed`.
    """
    s = values if isinstance(values, pd.Series) else pd.Series(values, dtype="object")
    report = ParseReport(total=len(s))
    cache: dict[Any, tuple[Decimal | None, str]] = {}

    def run(raw: Any, dec: str | None) -> tuple[Decimal | None, str]:
        key = (raw if isinstance(raw, str) else repr(raw), dec)
        if key not in cache:
            cache[key] = _parse(raw, dec)
        return cache[key]

    if decimal is None:
        votes = {",": 0, ".": 0}
        for raw in s.dropna().unique():
            st = _style(raw)
            if st:
                votes[st] += 1
        if votes[","] and votes["."]:
            report.notes["mixed"] = dict(votes)
        elif votes[","] or votes["."]:
            decimal = "," if votes[","] else "."
        report.notes["decimal"] = decimal
    out: list[Decimal | None] = []
    for idx, raw in zip(s.index, s.tolist(), strict=True):
        value, status = run(raw, decimal)
        if status == "empty":
            report.empty += 1
        elif status == "failed":
            report.failed.append((idx, str(raw)))
        else:
            report.parsed += 1
            if status == "ambiguous":
                report.ambiguous.append((idx, str(raw)))
        out.append(value)
    if as_decimal:
        res = pd.Series(out, index=s.index, dtype="object", name=s.name)
    else:
        res = pd.Series([None if v is None else float(v) for v in out], index=s.index, dtype="float64", name=s.name)
    return res, report


def _style(raw: Any) -> Literal[",", "."] | None:
    """Однозначный признак десятичного разделителя в значении, если он есть."""
    s, _ = _clean(raw)
    if not s or not re.fullmatch(r"[0-9.,]+", s):
        return None
    commas, dots = s.count(","), s.count(".")
    if commas and dots:
        return "," if s.rfind(",") > s.rfind(".") else "."
    if commas == 1 and not _GROUPS.fullmatch(s):
        return ","
    if dots == 1 and not _GROUPS.fullmatch(s):
        return "."
    return None


def to_number(
    values: pd.Series[Any] | list[Any],
    *,
    decimal: Literal[",", "."] | None = None,
    errors: Literal["coerce", "raise"] = "coerce",
    as_decimal: bool = False,
) -> pd.Series[Any]:
    """Как `parse_numbers`, но возвращает только столбец; отчёт лежит в `result.attrs['ru_report']`.

    С `errors='raise'` непонятное значение вызывает `ValueError`.
    """
    res, report = parse_numbers(values, decimal=decimal, as_decimal=as_decimal)
    if errors == "raise" and report.failed:
        idx, raw = report.failed[0]
        raise ValueError(f"не число: {raw!r} (строка {idx}); всего таких значений: {len(report.failed)}")
    res.attrs["ru_report"] = report
    return res


def format_number(
    value: float | Decimal | int | None,
    *,
    decimals: int | None = None,
    decimal: str = ",",
    thousands: str = "",
) -> str:
    """Записывает число в русском виде. Без `decimals` печатается кратчайшая запись, которая читается обратно без потерь."""
    if value is None or (isinstance(value, float) and value != value):
        return ""
    d = value if isinstance(value, Decimal) else Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    text = f"{d:.{decimals}f}" if decimals is not None else format(d.normalize(), "f")
    if "E" in text.upper():
        text = format(d, "f")
    neg = text.startswith("-")
    if neg:
        text = text[1:]
    int_part, _, frac = text.partition(".")
    if thousands:
        int_part = f"{int(int_part):,}".replace(",", thousands)
    out = int_part + (decimal + frac if frac else "")
    return "-" + out if neg else out
