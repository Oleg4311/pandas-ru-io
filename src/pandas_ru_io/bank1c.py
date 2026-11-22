"""Обмен «Клиент-банк — 1С» (текстовый формат `1CClientBankExchange`, обычно в cp1251): чтение выписок и запись платёжных документов."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from .dates import format_date, parse_date
from .encoding import EncodingGuess, decode_bytes
from .validators import account_error, bik_error, inn_error, kpp_error

__all__ = ["Statement", "read_1c", "validate_statement", "write_1c"]

_MAGIC = "1CClientBankExchange"
_DATE_FIELDS = {"Дата", "ДатаСписано", "ДатаПоступило", "ДатаНачала", "ДатаКонца", "ДатаСоздания", "ДатаПлатежа", "ДатаСоставления"}
_STRING_FIELDS_HINT = ("ИНН", "КПП", "БИК", "Счет", "Счёт", "РасчСчет", "Корсчет", "Номер", "Очередность", "ВидОплаты", "Код")
_MONEY_FIELDS = {"Сумма", "НачальныйОстаток", "КонечныйОстаток", "ВсегоПоступило", "ВсегоСписано"}


@dataclass
class Statement:
    """Содержимое файла обмена: заголовок, секции расчётных счетов и таблица документов."""

    header: dict[str, Any] = field(default_factory=dict)
    accounts: list[dict[str, str]] = field(default_factory=list)
    documents: pd.DataFrame = field(default_factory=pd.DataFrame)
    encoding: EncodingGuess | None = None
    warnings: list[str] = field(default_factory=list)


def _to_money(raw: str) -> float | None:
    raw = raw.strip().replace(" ", "").replace(",", ".")
    if not raw:
        return None
    try:
        return float(Decimal(raw))
    except InvalidOperation:
        return None


def _parse_lines(text: str) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]], list[str]]:
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [ln for ln in lines if ln != ""]
    if not lines or lines[0] != _MAGIC:
        raise ValueError(f"это не файл обмена с 1С: первая строка должна быть {_MAGIC!r}")
    header: dict[str, Any] = {}
    accounts: list[dict[str, str]] = []
    docs: list[dict[str, str]] = []
    warnings: list[str] = []
    mode = "header"
    cur: dict[str, str] = {}
    ended = False
    for n, ln in enumerate(lines[1:], start=2):
        if ln == "КонецФайла":
            ended = True
            break
        if ln == "СекцияРасчСчет":
            mode, cur = "account", {}
            continue
        if ln == "КонецРасчСчет":
            accounts.append(cur)
            mode, cur = "header", {}
            continue
        if ln.startswith("СекцияДокумент"):
            mode = "doc"
            cur = {"ТипДокумента": ln.partition("=")[2].strip()}
            continue
        if ln == "КонецДокумента":
            docs.append(cur)
            mode, cur = "header", {}
            continue
        key, eq, value = ln.partition("=")
        if not eq:
            warnings.append(f"строка {n}: нет знака «=», пропущена: {ln[:40]!r}")
            continue
        key, value = key.strip(), value.strip()
        if mode == "header":
            if key in header:
                prev = header[key]
                header[key] = [*prev, value] if isinstance(prev, list) else [prev, value]
            else:
                header[key] = value
        else:
            if key in cur:
                warnings.append(f"строка {n}: ключ {key} повторяется внутри секции, взято последнее значение")
            cur[key] = value
    if mode != "header":
        warnings.append("файл оборван посреди секции: последняя секция потеряна")
    if not ended:
        warnings.append("нет строки «КонецФайла»: файл мог быть обрезан")
    return header, accounts, docs, warnings


def _frame(docs: list[dict[str, str]]) -> pd.DataFrame:
    if not docs:
        return pd.DataFrame()
    columns: list[str] = []
    for d in docs:
        for k in d:
            if k not in columns:
                columns.append(k)
    df = pd.DataFrame([{k: d.get(k, "") for k in columns} for d in docs], columns=columns, dtype="object")
    for col in columns:
        if col in _DATE_FIELDS:
            df[col] = pd.to_datetime(pd.Series([parse_date(v) for v in df[col]], dtype="object"), errors="coerce")
        elif col in _MONEY_FIELDS:
            df[col] = pd.Series([_to_money(v) for v in df[col]], dtype="float64")
        else:
            df[col] = df[col].astype("string")
    return df


def read_1c(source: str | Path | bytes | io.IOBase, *, encoding: str | None = None) -> Statement:
    """Читает файл обмена с 1С из пути, байтов или файлового объекта. Кодировка определяется сама (чаще всего cp1251)."""
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and not source.startswith(_MAGIC) and source != ""):
        data = Path(source).read_bytes()
    elif isinstance(source, bytes):
        data = source
    elif isinstance(source, str):
        data = source.encode("utf-8")
        encoding = encoding or "utf-8"
    else:
        raw = source.read()
        data = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
    text, guess = decode_bytes(data, encoding=encoding)
    header, accounts, docs, warnings = _parse_lines(text)
    return Statement(header=header, accounts=accounts, documents=_frame(docs), encoding=guess, warnings=warnings)


def _fmt(col: str, value: Any) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if col in _DATE_FIELDS:
        return format_date(value if isinstance(value, (datetime, pd.Timestamp)) else parse_date(value), with_time=False)
    if col in _MONEY_FIELDS:
        return f"{Decimal(repr(float(value))):.2f}"
    return str(value)


def write_1c(
    documents: pd.DataFrame,
    *,
    header: dict[str, Any] | None = None,
    accounts: list[dict[str, str]] | None = None,
) -> bytes:
    """Записывает файл обмена в cp1251 с переводами строк CRLF (как ожидает 1С). Читается обратно через `read_1c` без потерь.

    Нужен столбец `ТипДокумента` (по умолчанию «Платежное поручение»). Суммы пишутся с двумя знаками и точкой.
    Символы, которых нет в cp1251, вызывают `UnicodeEncodeError` с указанием места.
    """
    head: dict[str, Any] = {"ВерсияФормата": "1.03", "Кодировка": "Windows", **(header or {})}
    lines = [_MAGIC]
    for key, value in head.items():
        for v in value if isinstance(value, list) else [value]:
            lines.append(f"{key}={v}")
    for acc in accounts or []:
        lines.append("СекцияРасчСчет")
        lines.extend(f"{k}={v}" for k, v in acc.items())
        lines.append("КонецРасчСчет")
    for _, row in documents.iterrows():
        kind = row.get("ТипДокумента", "Платежное поручение")
        kind = "Платежное поручение" if kind is None or pd.isna(kind) else str(kind)
        lines.append(f"СекцияДокумент={kind}")
        for col in documents.columns:
            if col == "ТипДокумента":
                continue
            text = _fmt(str(col), row[col])
            if text != "":
                lines.append(f"{col}={text}")
        lines.append("КонецДокумента")
    lines.append("КонецФайла")
    body = "\r\n".join(lines) + "\r\n"
    try:
        return body.encode("cp1251")
    except UnicodeEncodeError as e:
        bad = body[e.start : e.end]
        line = body.count("\n", 0, e.start) + 1
        raise UnicodeEncodeError("cp1251", body, e.start, e.end, f"символ {bad!r} (строка {line}) не помещается в cp1251: замените его") from None


def validate_statement(documents: pd.DataFrame) -> pd.DataFrame:
    """Проверяет реквизиты документов: ИНН, КПП, БИК, расчётные счета по БИК, сумму. Возвращает таблицу замечаний (пустую, если всё верно).

    Столбцы результата: `строка` (индекс документа), `поле`, `значение`, `замечание`.
    """
    issues: list[dict[str, Any]] = []

    def add(idx: Any, field_name: str, value: Any, problem: str | None) -> None:
        if problem:
            issues.append({"строка": idx, "поле": field_name, "значение": value, "замечание": problem})

    def get(row: pd.Series, name: str) -> str:
        v = row.get(name)
        return "" if v is None or pd.isna(v) else str(v).strip()

    for idx, row in documents.iterrows():
        for side in ("Плательщик", "Получатель"):
            inn = get(row, f"{side}ИНН")
            if inn:
                add(idx, f"{side}ИНН", inn, inn_error(inn))
            kpp = get(row, f"{side}КПП")
            if kpp:
                add(idx, f"{side}КПП", kpp, kpp_error(kpp))
            bik = get(row, f"{side}БИК")
            if bik:
                add(idx, f"{side}БИК", bik, bik_error(bik))
            acc = get(row, f"{side}РасчСчет") or get(row, f"{side}Счет")
            if acc and bik and not bik_error(bik):
                add(idx, f"{side}РасчСчет", acc, account_error(acc, bik))
        if "Сумма" in documents.columns:
            total = row.get("Сумма")
            if total is None or pd.isna(total):
                add(idx, "Сумма", "", "сумма не указана")
            elif float(total) <= 0:
                add(idx, "Сумма", total, "сумма должна быть положительной")
    return pd.DataFrame(issues, columns=["строка", "поле", "значение", "замечание"])
