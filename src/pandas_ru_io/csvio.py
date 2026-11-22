"""Чтение и запись CSV в том виде, в каком их делает русский Excel: кодировка cp1251, разделитель «;», запятая в дробях, даты «дд.мм.гггг»."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from .dates import format_date, parse_dates
from .encoding import decode_bytes
from .numbers import format_number, parse_numbers
from .report import ParseReport

__all__ = ["read_csv_ru", "sniff_delimiter", "to_csv_ru"]

_DELIMITERS = (";", "\t", ",", "|")
_CODE_NAME = re.compile(r"(?i)инн|кпп|бик|снилс|огрн|сч[её]т|р/с|к/с|корр|телефон|тел\.|индекс|артикул|штрих|код|номер|№|id\b")
_THRESHOLD = 0.95
_NUM_SHAPE = re.compile(r"[\s (+\-−–]*\d[\d\s .,]*[)\s %]*(?:₽|руб\.?|р\.?|rub)?\s*", re.I)
_DATE_SHAPE = re.compile(
    r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}(?:[ t,]+\d{1,2}:\d{2}(?::\d{2})?)?|\d{4}-\d{2}-\d{2}(?:[ t]\d{2}:\d{2}(?::\d{2})?)?(?:z|[+-]\d{2}:?\d{2})?|\d{1,2}\s+[а-яё]+\.?\s+\d{4}(?:\s*г\.?)?",
    re.I,
)


def sniff_delimiter(text: str, sample_lines: int = 60) -> str:
    """Выбирает разделитель по тому, какой даёт одинаковое число столбцов (больше одного) в первых строках; при равенстве предпочитает «;»."""
    sample = "\n".join(text.splitlines()[:sample_lines])
    best = ";"
    best_key: tuple[float, int] = (-1.0, 0)
    for d in _DELIMITERS:
        try:
            rows = [r for r in csv.reader(io.StringIO(sample), delimiter=d) if r]
        except csv.Error:
            continue
        if not rows:
            continue
        counts = Counter(len(r) for r in rows)
        width, freq = counts.most_common(1)[0]
        if width < 2:
            continue
        key = (freq / len(rows), width)
        if key > best_key:
            best_key, best = key, d
    return best


def _read_source(source: str | Path | bytes | io.IOBase) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    raw = source.read()
    return raw if isinstance(raw, bytes) else str(raw).encode("utf-8")


def _dedupe(names: list[str]) -> list[str]:
    seen: Counter[str] = Counter()
    out = []
    for n in names:
        n = n.strip() or "столбец"
        out.append(n if seen[n] == 0 else f"{n}.{seen[n]}")
        seen[n] += 1
    return out


def _is_code(name: str, values: list[str]) -> str | None:
    if _CODE_NAME.search(name):
        return "название столбца похоже на код или номер"
    digits = [v for v in values if v.isdigit()]
    if any(len(v) > 1 and v.startswith("0") for v in digits):
        return "есть значения с ведущим нулём"
    if any(len(v) >= 12 for v in digits):
        return "есть длинные числа без дробной части (счета, ИНН): превращать их в число нельзя"
    return None


def read_csv_ru(
    source: str | Path | bytes | io.IOBase,
    *,
    encoding: str | None = None,
    sep: str | None = None,
    decimal: str | None = None,
    header: bool = True,
    parse_dates_: bool = True,
) -> pd.DataFrame:
    """Читает CSV: сама определяет кодировку и разделитель, разбирает русские числа и даты, не ломает коды.

    Столбец становится числом или датой, только если так читаются не менее 95% непустых значений; коды (ИНН, счета, значения с
    ведущим нулём, длинные числа) остаются строками. Пустые ячейки превращаются в пропуски.
    Подробности разбора лежат в `df.attrs['ru']`: кодировка, разделитель и по каждому столбцу вид, причина и `ParseReport`.
    """
    data = _read_source(source)
    text, guess = decode_bytes(data, encoding=encoding)
    delim = sep or sniff_delimiter(text)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if r and any(c.strip() for c in r)]
    if not rows:
        return pd.DataFrame()
    width = max(len(r) for r in rows)
    padded = [r + [""] * (width - len(r)) for r in rows]
    names = _dedupe(padded[0]) if header else [f"столбец{i}" for i in range(width)]
    body = padded[1:] if header else padded
    ragged = sum(1 for r in rows if len(r) != width)
    raw = pd.DataFrame(body, columns=names, dtype="object") if body else pd.DataFrame(columns=names, dtype="object")
    info: dict[str, Any] = {"encoding": guess, "sep": delim, "ragged_rows": ragged, "columns": {}}
    out: dict[str, pd.Series[Any]] = {}
    for col in names:
        cells = raw[col].map(lambda v: v.strip() if isinstance(v, str) else v)
        nonempty = [c for c in cells if c != ""]
        kind, reason, report = "str", "обычный текст", ParseReport(total=len(cells), parsed=len(nonempty), empty=len(cells) - len(nonempty))
        result: pd.Series[Any] = cells.replace("", pd.NA).astype("string")
        if nonempty:
            code_reason = _is_code(col, nonempty)
            if code_reason:
                reason = code_reason
            else:
                share_num = sum(1 for c in nonempty if _NUM_SHAPE.fullmatch(c)) / len(nonempty)
                share_date = sum(1 for c in nonempty if _DATE_SHAPE.fullmatch(c)) / len(nonempty)
                if parse_dates_ and share_date >= _THRESHOLD:
                    dts, drep = parse_dates(cells.where(cells != "", None))
                    kind, reason, report, result = "date", f"по виду даты: {len(nonempty) - len(drep.failed)} из {len(nonempty)} разобраны", drep, dts
                elif share_num >= _THRESHOLD:
                    nums, rep = parse_numbers(cells.where(cells != "", None), decimal="," if decimal == "," else "." if decimal == "." else None)
                    kind, reason, report, result = (
                        "number",
                        f"по виду числа: {len(nonempty) - len(rep.failed)} из {len(nonempty)} разобраны",
                        rep,
                        nums,
                    )
                    if rep.parsed and not rep.failed and (nums.dropna() % 1 == 0).all() and not any(re.search(r"[.,]\d", c) for c in nonempty):
                        result = nums.astype("Int64") if nums.abs().max() < 2**53 else nums
        info["columns"][col] = {"kind": kind, "reason": reason, "report": report}
        out[col] = result
    df = pd.DataFrame(out)
    df.attrs["ru"] = info
    return df


def _cell(value: Any, *, decimal: str, date_format: str | None, column_times: bool) -> str:
    if value is None or value is pd.NA or (isinstance(value, float) and value != value) or value is pd.NaT:
        return ""
    if isinstance(value, (pd.Timestamp,)) or hasattr(value, "strftime"):
        if date_format is not None:
            return value.strftime(date_format)
        return format_date(value, with_time=column_times)
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return format_number(value, decimal=decimal)
    if hasattr(value, "item") and not isinstance(value, str):
        return _cell(value.item(), decimal=decimal, date_format=date_format, column_times=column_times)
    return str(value)


def to_csv_ru(
    df: pd.DataFrame,
    path: str | Path | None = None,
    *,
    encoding: str = "cp1251",
    sep: str = ";",
    decimal: str = ",",
    date_format: str | None = None,
    header: bool = True,
    errors: str = "strict",
) -> bytes | None:
    """Записывает DataFrame так, как его ждёт русский Excel: cp1251 (или utf-8-sig), «;», запятая в дробях, даты «дд.мм.гггг».

    Без `path` возвращает байты. `errors='strict'` при символе, которого нет в кодировке (эмодзи в cp1251), поднимает ошибку с названием
    столбца и строки; `errors='replace'` заменяет такие символы на «?». Булевы значения пишутся «Да» и «Нет».
    """
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=sep, lineterminator="\r\n")
    times = {c: bool(pd.api.types.is_datetime64_any_dtype(df[c]) and (df[c].dropna().dt.normalize() != df[c].dropna()).any()) for c in df.columns}
    if header:
        writer.writerow([str(c) for c in df.columns])
    for row in df.itertuples(index=False):
        writer.writerow([_cell(v, decimal=decimal, date_format=date_format, column_times=times[c]) for c, v in zip(df.columns, row, strict=True)])
    text = out.getvalue()
    if errors == "strict":
        try:
            data = text.encode(encoding)
        except UnicodeEncodeError as e:
            lines = text.split("\r\n")
            line_no = text.count("\r\n", 0, e.start)
            col_hint = ""
            if line_no >= 0 and line_no < len(lines):
                col_hint = f" (строка {line_no + 1}: {lines[line_no][:60]!r})"
            raise UnicodeEncodeError(
                encoding, text, e.start, e.end, f"символ {text[e.start : e.end]!r} не помещается в {encoding}{col_hint}"
            ) from None
    else:
        data = text.encode(encoding, errors=errors)
    if path is None:
        return data
    Path(path).write_bytes(data)
    return None
