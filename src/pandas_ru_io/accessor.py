"""Аксессор `.ru` для Series и DataFrame: `s.ru.to_number()`, `s.ru.to_datetime()`, `s.ru.valid('inn')`, `df.ru.to_csv(...)`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from . import validators
from .csvio import to_csv_ru
from .dates import to_datetime
from .numbers import to_number

_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "inn": validators.is_inn,
    "snils": validators.is_snils,
    "ogrn": validators.is_ogrn,
    "ogrnip": validators.is_ogrnip,
    "kpp": validators.is_kpp,
    "bik": validators.is_bik,
}


@pd.api.extensions.register_series_accessor("ru")
class RuSeriesAccessor:
    """Методы для столбца с русскими данными."""

    def __init__(self, series: pd.Series[Any]) -> None:
        self._s = series

    def to_number(self, *, decimal: Literal[",", "."] | None = None, errors: Literal["coerce", "raise"] = "coerce") -> pd.Series[Any]:
        """Числа в русской записи → float64. Отчёт: `result.attrs['ru_report']`."""
        return to_number(self._s, decimal=decimal, errors=errors)

    def to_datetime(self, *, excel: bool = False, errors: Literal["coerce", "raise"] = "coerce") -> pd.Series[Any]:
        """Даты в русской записи → datetime64. Отчёт: `result.attrs['ru_report']`."""
        return to_datetime(self._s, excel=excel, errors=errors)

    def valid(self, kind: str) -> pd.Series[Any]:
        """Булев ряд: верен ли реквизит (`'inn'`, `'snils'`, `'ogrn'`, `'ogrnip'`, `'kpp'`, `'bik'`). Пропуск даёт `False`."""
        if kind not in _VALIDATORS:
            raise ValueError(f"неизвестный вид реквизита {kind!r}; доступны: {', '.join(_VALIDATORS)}")
        check = _VALIDATORS[kind]
        return self._s.map(lambda v: bool(isinstance(v, str) and check(v)))

    def problems(self, kind: str) -> pd.Series[Any]:
        """Текст замечания по каждому значению или пропуск, если реквизит верен."""
        errs = {
            "inn": validators.inn_error,
            "snils": validators.snils_error,
            "ogrn": validators.ogrn_error,
            "ogrnip": validators.ogrnip_error,
            "kpp": validators.kpp_error,
            "bik": validators.bik_error,
        }
        if kind not in errs:
            raise ValueError(f"неизвестный вид реквизита {kind!r}; доступны: {', '.join(errs)}")
        return self._s.map(lambda v: errs[kind](v))


@pd.api.extensions.register_dataframe_accessor("ru")
class RuDataFrameAccessor:
    """Методы для таблицы."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def to_csv(self, path: str | Path | None = None, **kwargs: Any) -> bytes | None:
        """CSV для русского Excel (cp1251, «;», запятая в дробях); см. `to_csv_ru`."""
        return to_csv_ru(self._df, path, **kwargs)
