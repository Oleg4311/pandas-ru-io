"""pandas-ru-io: русские табличные данные в pandas.

Подключение регистрирует аксессор `.ru` у Series и DataFrame:

    import pandas as pd, pandas_ru_io as ru
    df = ru.read_csv_ru("выписка.csv")          # кодировка, разделитель, числа и даты определяются сами
    df["Сумма"].ru.to_number()                  # «1 234,56» → 1234.56
    df["ИНН"].ru.valid("inn")                   # проверка контрольных цифр
"""

from . import accessor as _accessor  # noqa: F401  (регистрирует аксессор .ru)
from .bank1c import Statement, read_1c, validate_statement, write_1c
from .csvio import read_csv_ru, sniff_delimiter, to_csv_ru
from .dates import MONTHS, format_date, parse_date, parse_dates, to_datetime
from .encoding import EncodingGuess, decode_bytes, detect_encoding
from .numbers import format_number, parse_number, parse_numbers, to_number
from .report import ParseReport
from .validators import (
    account_error,
    bik_error,
    inn_error,
    is_account,
    is_bik,
    is_inn,
    is_kpp,
    is_ogrn,
    is_ogrnip,
    is_snils,
    kpp_error,
    ogrn_error,
    ogrnip_error,
    snils_error,
)

__version__ = "0.1.0"

__all__ = [
    "MONTHS",
    "EncodingGuess",
    "ParseReport",
    "Statement",
    "account_error",
    "bik_error",
    "decode_bytes",
    "detect_encoding",
    "format_date",
    "format_number",
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
    "parse_date",
    "parse_dates",
    "parse_number",
    "parse_numbers",
    "read_1c",
    "read_csv_ru",
    "sniff_delimiter",
    "snils_error",
    "to_csv_ru",
    "to_datetime",
    "to_number",
    "validate_statement",
    "write_1c",
]
