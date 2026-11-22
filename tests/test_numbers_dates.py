from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import pandas_ru_io as ru
from pandas_ru_io import format_date, format_number, parse_date, parse_dates, parse_number, parse_numbers, to_datetime, to_number


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("1 234,56", "1234.56"),
        ("1 234,56", "1234.56"),
        ("1 234,56", "1234.56"),
        ("1 234 567,8", "1234567.8"),
        ("(1 000,00)", "-1000.00"),
        ("−5,5", "-5.5"),
        ("–5,5", "-5.5"),
        ("+7,5", "7.5"),
        ("12,5 руб.", "12.5"),
        ("100 ₽", "100"),
        ("₽ 100", "100"),
        ("руб. 5,5", "5.5"),
        ("15%", "15"),
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("1.234.567", "1234567"),
        ("1,234,567", "1234567"),
        ("5,", "5"),
        (",5", "0.5"),
        ("0,001", "0.001"),
        (1234.5, "1234.5"),
        (7, "7"),
    ],
)
def test_parse_number_variants(raw: object, want: str) -> None:
    assert parse_number(raw) == Decimal(want)


@pytest.mark.parametrize(
    "raw", ["", "  ", "-", "—", "н/д", "nan", "abc", "1 2 3", "12 34", "12,345,6", "1,2,3", "1..2", "--5", "5-5", "12abc", "₽", None, float("nan")]
)
def test_parse_number_rejects_or_treats_as_empty(raw: object) -> None:
    assert parse_number(raw) is None


def test_ambiguous_thousands_versus_decimal_is_resolved_by_the_column() -> None:
    col = ["1 234,56", "3,5", "1,234"]
    res, rep = parse_numbers(col)
    assert rep.notes["decimal"] == ","
    assert res.tolist() == [1234.56, 3.5, 1.234]
    assert rep.ambiguous == []  # запятая в столбце десятичная, «1,234» однозначно 1,234
    res2, rep2 = parse_numbers(["1,234.50", "2,500.00", "1,234"])
    assert rep2.notes["decimal"] == "."
    assert res2.tolist() == [1234.5, 2500.0, 1234.0]  # здесь запятая — разделитель тысяч
    res3, rep3 = parse_numbers(["1,234", "1.234"])
    assert [i for i, _ in rep3.ambiguous] == [0, 1]
    assert res3.tolist() == [1.234, 1.234]
    assert "decimal" in rep3.notes and rep3.notes["decimal"] is None


def test_mixed_styles_are_reported_not_hidden() -> None:
    _, rep = parse_numbers(["1,5", "2.5"])
    assert rep.notes["mixed"] == {",": 1, ".": 1}


def test_to_number_reports_failures_and_can_raise() -> None:
    s = pd.Series(["10", "abc", "", "2,5"], index=[10, 11, 12, 13])
    res = to_number(s)
    assert res.isna().tolist() == [False, True, True, False]
    report = res.attrs["ru_report"]
    assert report.failed == [(11, "abc")]
    assert report.empty == 1
    assert report.parsed == 2
    assert not report.ok
    with pytest.raises(ValueError, match=r"не число: 'abc' \(строка 11\)"):
        to_number(s, errors="raise")
    assert to_number(pd.Series(["1", "2"]), errors="raise").tolist() == [1.0, 2.0]


def test_as_decimal_keeps_exact_values() -> None:
    res = to_number(pd.Series(["0,1", "0,2"]), as_decimal=True)
    assert sum(res.tolist()) == Decimal("0.3")
    assert sum(to_number(pd.Series(["0,1", "0,2"])).tolist()) != 0.3  # float не точен, поэтому режим нужен


@given(
    st.decimals(min_value=Decimal("-999999999.99"), max_value=Decimal("999999999.99"), places=2, allow_nan=False, allow_infinity=False),
    st.sampled_from(["", " ", " ", " "]),
)
@settings(max_examples=400)
def test_format_then_parse_roundtrip(value: Decimal, thousands: str) -> None:
    text = format_number(value, decimals=2, thousands=thousands)
    assert parse_number(text) == value


@given(st.decimals(min_value=Decimal("-1e12"), max_value=Decimal("1e12"), places=6, allow_nan=False, allow_infinity=False))
@settings(max_examples=400)
def test_shortest_format_is_lossless(value: Decimal) -> None:
    assert parse_number(format_number(value)) == value
    assert parse_number(format_number(value, decimal=".")) == value


@given(st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False))
@settings(max_examples=400)
def test_float_roundtrip_is_exact(x: float) -> None:
    assert float(parse_number(format_number(x)) or 0) == x


def test_format_number_details() -> None:
    assert format_number(1234.5, thousands=" ") == "1 234,5"
    assert format_number(-0.1) == "-0,1"
    assert format_number(1e-7) == "0,0000001"
    assert format_number(12345678901234567890) == "12345678901234567890"
    assert format_number(2, decimals=2) == "2,00"
    assert format_number(None) == ""
    assert format_number(float("nan")) == ""
    assert format_number(Decimal("1E+3")) == "1000"


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("05.01.2024", datetime(2024, 1, 5)),
        ("5.1.2024", datetime(2024, 1, 5)),
        ("05/01/2024", datetime(2024, 1, 5)),
        ("05-01-2024", datetime(2024, 1, 5)),
        ("05.01.24", datetime(2024, 1, 5)),
        ("05.01.70", datetime(1970, 1, 5)),
        ("05.01.69", datetime(2069, 1, 5)),
        ("05.01.2024 10:30", datetime(2024, 1, 5, 10, 30)),
        ("05.01.2024, 10:30:15", datetime(2024, 1, 5, 10, 30, 15)),
        ("2024-01-05", datetime(2024, 1, 5)),
        ("2024-01-05T10:30:15", datetime(2024, 1, 5, 10, 30, 15)),
        ("2024-01-05 10:30:15.123", datetime(2024, 1, 5, 10, 30, 15)),
        ("2024-01-05T10:30:15+03:00", datetime(2024, 1, 5, 10, 30, 15)),
        ("20240105", datetime(2024, 1, 5)),
        ("5 января 2024", datetime(2024, 1, 5)),
        ("5 января 2024 г.", datetime(2024, 1, 5)),
        ("05 янв. 2024", datetime(2024, 1, 5)),
        ("5 мая 2024 года 14:05", datetime(2024, 5, 5, 14, 5)),
        ("Январь 2024", datetime(2024, 1, 1)),
        ("сентября 2023", datetime(2023, 9, 1)),
        ("29 февраля 2024", datetime(2024, 2, 29)),
        (datetime(2024, 1, 5), datetime(2024, 1, 5)),
        (pd.Timestamp("2024-01-05"), datetime(2024, 1, 5)),
    ],
)
def test_parse_date_variants(raw: object, want: datetime | None) -> None:
    assert parse_date(raw) == want


@pytest.mark.parametrize(
    "raw",
    [
        "31.02.2024",
        "29.02.2023",
        "32.01.2024",
        "00.01.2024",
        "05.13.2024",
        "5 январья 2024",
        "abc",
        "",
        "—",
        "05.01",
        "24:00",
        None,
        float("nan"),
        True,
        45000,
    ],
)
def test_parse_date_rejects_impossible_dates(raw: object) -> None:
    assert parse_date(raw) is None


def test_excel_serial_numbers() -> None:
    assert parse_date(45296, excel=True) == datetime(2024, 1, 5)
    assert parse_date("45296", excel=True) == datetime(2024, 1, 5)
    assert parse_date(45296.5, excel=True) == datetime(2024, 1, 5, 12)
    assert parse_date(59, excel=True) == datetime(1900, 2, 28)
    assert parse_date(60, excel=True) is None, "29.02.1900 есть только в Excel"
    assert parse_date(61, excel=True) == datetime(1900, 3, 1)
    assert parse_date(1, excel=True) == datetime(1900, 1, 1)
    assert parse_date(0, excel=True) is None
    assert parse_date(45296) is None  # без excel=True число не превращается в дату


def test_parse_dates_reports_failures_and_keeps_nat() -> None:
    res, rep = parse_dates(pd.Series(["05.01.2024", "31.02.2024", "", "6 января 2024"], index=list("abcd")))
    assert res.isna().tolist() == [False, True, True, False]
    assert rep.failed == [("b", "31.02.2024")]
    assert rep.empty == 1
    assert rep.parsed == 2
    assert str(res.dtype).startswith("datetime64")
    with pytest.raises(ValueError, match="не дата: '31.02.2024'"):
        to_datetime(["05.01.2024", "31.02.2024"], errors="raise")


@given(st.datetimes(min_value=datetime(1900, 1, 1), max_value=datetime(2099, 12, 31)))
@settings(max_examples=400)
def test_format_then_parse_roundtrip_for_dates(dt: datetime) -> None:
    dt = dt.replace(microsecond=0)
    assert parse_date(format_date(dt, with_time=True)) == dt
    assert parse_date(format_date(dt.replace(hour=0, minute=0, second=0))) == dt.replace(hour=0, minute=0, second=0)


def test_format_date_time_part_only_when_needed() -> None:
    assert format_date(datetime(2024, 1, 5)) == "05.01.2024"
    assert format_date(datetime(2024, 1, 5, 10, 30)) == "05.01.2024 10:30:00"
    assert format_date(None) == ""
    assert format_date(pd.NaT) == ""  # type: ignore[arg-type]


def test_every_month_name_form_is_parsed() -> None:
    for form, n in ru.MONTHS.items():
        assert parse_date(f"15 {form} 2024") == datetime(2024, n, 15), form
