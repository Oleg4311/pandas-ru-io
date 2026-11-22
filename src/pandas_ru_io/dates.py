"""Даты в русской записи: «05.01.2024», «5 января 2024 г.», «05.01.24 10:30», ISO, «20240105», серийные числа Excel."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from .report import ParseReport

__all__ = ["MONTHS", "format_date", "parse_date", "parse_dates", "to_datetime"]

_MONTH_FORMS: dict[int, tuple[str, ...]] = {
    1: ("январь", "января", "янв"),
    2: ("февраль", "февраля", "фев", "февр"),
    3: ("март", "марта", "мар"),
    4: ("апрель", "апреля", "апр"),
    5: ("май", "мая"),
    6: ("июнь", "июня", "июн"),
    7: ("июль", "июля", "июл"),
    8: ("август", "августа", "авг"),
    9: ("сентябрь", "сентября", "сен", "сент"),
    10: ("октябрь", "октября", "окт"),
    11: ("ноябрь", "ноября", "ноя", "нояб"),
    12: ("декабрь", "декабря", "дек"),
}
MONTHS: dict[str, int] = {form: n for n, forms in _MONTH_FORMS.items() for form in forms}

_TIME = r"(?:[ t,]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?"
_DMY = re.compile(rf"(\d{{1,2}})[./-](\d{{1,2}})[./-](\d{{4}}|\d{{2}}){_TIME}")
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[ t](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?(?:z|[+-]\d{2}:?\d{2})?")
_COMPACT = re.compile(r"(\d{4})(\d{2})(\d{2})")
_WORDS = re.compile(rf"(\d{{1,2}})\s+([а-яё]+)\.?\s+(\d{{4}})(?:\s*(?:г\.?|года))?{_TIME}")
_MONTH_YEAR = re.compile(r"([а-яё]+)\.?\s+(\d{4})(?:\s*(?:г\.?|года))?")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_EXCEL_EPOCH = datetime(1899, 12, 30)
_EMPTY = {"", "-", "—", "–", "н/д", "нд", "nan", "nat", "none", "null"}


def _make(y: int, m: int, d: int, hh: str | None = None, mm: str | None = None, ss: str | None = None) -> datetime | None:
    try:
        return datetime(y, m, d, int(hh or 0), int(mm or 0), int(ss or 0))
    except ValueError:
        return None


def _year(text: str) -> int:
    y = int(text)
    if len(text) == 2:
        return 2000 + y if y < 70 else 1900 + y  # как %y в strptime
    return y


def _excel(value: float) -> datetime | None:
    # Excel считает 1900 високосным: серийные числа до 60 сдвинуты на день относительно настоящих дат
    if not 1 <= value < 2958466:
        return None
    if 60 <= value < 61:
        return None  # 29.02.1900 существует только в Excel (он считает 1900 високосным)
    if value < 60:
        value += 1
    return _EXCEL_EPOCH + timedelta(days=value)


def parse_date(raw: Any, *, excel: bool = False) -> datetime | None:
    """Разбирает одну дату; `None` для пустого и непонятного значения (в том числе 31.02.2024).

    Порядок всегда «день, месяц, год». Двузначный год: 00–69 это 2000–2069, 70–99 это 1970–1999.
    Часовой пояс в ISO-записи отбрасывается. `excel=True` разрешает читать числа как серийные даты Excel.
    """
    if raw is None or (isinstance(raw, float) and raw != raw):
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, pd.Timestamp):
        return None if pd.isna(raw) else raw.to_pydatetime()
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return _excel(float(raw)) if excel else None
    s = str(raw).strip().lower().replace(" ", " ")
    if s in _EMPTY:
        return None
    if (m := _DMY.fullmatch(s)) is not None:
        return _make(_year(m[3]), int(m[2]), int(m[1]), m[4], m[5], m[6])
    if (m := _ISO.fullmatch(s)) is not None:
        return _make(int(m[1]), int(m[2]), int(m[3]), m[4], m[5], m[6])
    if (m := _WORDS.fullmatch(s)) is not None and m[2] in MONTHS:
        return _make(int(m[3]), MONTHS[m[2]], int(m[1]), m[4], m[5], m[6])
    if (m := _MONTH_YEAR.fullmatch(s)) is not None and m[1] in MONTHS:
        return _make(int(m[2]), MONTHS[m[1]], 1)
    if (m := _COMPACT.fullmatch(s)) is not None:
        return _make(int(m[1]), int(m[2]), int(m[3]))
    if excel and _NUMBER.fullmatch(s):
        return _excel(float(s.replace(",", ".")))
    return None


def parse_dates(values: pd.Series[Any] | list[Any], *, excel: bool = False) -> tuple[pd.Series[Any], ParseReport]:
    """Разбирает столбец дат: возвращает (datetime64[ns], отчёт). Непонятные значения становятся NaT и попадают в `report.failed`."""
    s = values if isinstance(values, pd.Series) else pd.Series(values, dtype="object")
    report = ParseReport(total=len(s))
    cache: dict[Any, datetime | None] = {}
    out: list[datetime | None] = []
    for idx, raw in zip(s.index, s.tolist(), strict=True):
        key = raw if isinstance(raw, str) else repr(raw)
        if key not in cache:
            cache[key] = parse_date(raw, excel=excel)
        value = cache[key]
        empty = raw is None or (isinstance(raw, float) and raw != raw) or (isinstance(raw, str) and raw.strip().lower() in _EMPTY)
        if value is None and empty:
            report.empty += 1
        elif value is None:
            report.failed.append((idx, str(raw)))
        else:
            report.parsed += 1
        out.append(value)
    res = pd.to_datetime(pd.Series(out, dtype="object"), errors="coerce")
    res.index = s.index  # индекс присваивается, а не выравнивается: иначе при нестандартном индексе всё станет NaT
    res.name = s.name
    return res, report


def to_datetime(values: pd.Series[Any] | list[Any], *, excel: bool = False, errors: str = "coerce") -> pd.Series[Any]:
    """Как `parse_dates`, но возвращает только столбец; отчёт лежит в `result.attrs['ru_report']`. С `errors='raise'` ошибка вызывает `ValueError`."""
    res, report = parse_dates(values, excel=excel)
    if errors == "raise" and report.failed:
        idx, raw = report.failed[0]
        raise ValueError(f"не дата: {raw!r} (строка {idx}); всего таких значений: {len(report.failed)}")
    res.attrs["ru_report"] = report
    return res


def format_date(value: datetime | pd.Timestamp | None, *, with_time: bool | None = None) -> str:
    """«05.01.2024» (время добавляется, если оно не полночь или `with_time=True`)."""
    if value is None or pd.isna(value):
        return ""
    show = with_time if with_time is not None else (value.hour, value.minute, value.second) != (0, 0, 0)
    return value.strftime("%d.%m.%Y %H:%M:%S" if show else "%d.%m.%Y")
