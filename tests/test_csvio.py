from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import pandas_ru_io as ru
from pandas_ru_io import read_csv_ru, sniff_delimiter, to_csv_ru

EXCEL = (
    "Дата;Контрагент;ИНН;Сумма;Количество;Комментарий\r\n"
    "05.01.2024;ООО «Ромашка»;7707083893;1 234,56;3;аванс\r\n"
    "06.01.2024;ИП Иванов;0012345678;(500,00);12;возврат\r\n"
    "07.01.2024;ООО Вектор;500100732259;12,5 руб.;;\r\n"
)


def test_reads_what_russian_excel_writes() -> None:
    df = read_csv_ru(EXCEL.encode("cp1251"))
    info = df.attrs["ru"]
    assert info["encoding"].encoding == "cp1251"
    assert info["sep"] == ";"
    assert str(df["Дата"].dtype).startswith("datetime64")
    assert df["Дата"].tolist() == [pd.Timestamp("2024-01-05"), pd.Timestamp("2024-01-06"), pd.Timestamp("2024-01-07")]
    assert df["Сумма"].tolist() == [1234.56, -500.0, 12.5]
    assert df["Количество"].dtype == "Int64"
    assert df["Количество"].tolist()[:2] == [3, 12]
    assert pd.isna(df["Количество"].iloc[2])
    assert df["ИНН"].tolist() == ["7707083893", "0012345678", "500100732259"], "ведущий ноль и длинные числа не теряются"
    assert df["Контрагент"].tolist()[0] == "ООО «Ромашка»"
    assert pd.isna(df["Комментарий"].iloc[2])
    assert info["columns"]["ИНН"]["kind"] == "str"
    assert info["columns"]["Сумма"]["kind"] == "number"
    assert info["columns"]["Дата"]["kind"] == "date"


def test_failed_cells_become_missing_and_are_reported_per_column() -> None:
    text = "Дата;Сумма\r\n05.01.2024;1\r\n31.02.2024;2\r\n07.01.2024;абв\r\n08.01.2024;4\r\n09.01.2024;5\r\n10.01.2024;6\r\n"
    text += "".join(f"{d:02d}.01.2024;{d}\r\n" for d in range(11, 28))
    df = read_csv_ru(text.encode("cp1251"))
    cols = df.attrs["ru"]["columns"]
    assert cols["Дата"]["report"].failed == [(1, "31.02.2024")]
    assert pd.isna(df["Дата"].iloc[1])
    assert cols["Сумма"]["report"].failed == [(2, "абв")]
    assert df["Сумма"].isna().sum() == 1


def test_a_text_column_that_looks_a_little_like_numbers_stays_text() -> None:
    rows = "\r\n".join(f"Товар {i};{'12' if i < 3 else 'много'}" for i in range(20))
    df = read_csv_ru(f"Название;Описание\r\n{rows}\r\n".encode("cp1251"))
    assert df.attrs["ru"]["columns"]["Описание"]["kind"] == "str"


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("a;b;c\n1;2;3\n4;5;6", ";"),
        ("a,b,c\n1,2,3\n4,5,6", ","),
        ("a\tb\n1\t2\n3\t4", "\t"),
        ("a|b|c\n1|2|3", "|"),
        ("abc\ndef", ";"),
        ("a;b\n1,5;2,5\n3,5;4,5", ";"),
    ],
)
def test_sniff_delimiter(text: str, want: str) -> None:
    assert sniff_delimiter(text) == want


def test_quoted_delimiters_and_multiline_cells() -> None:
    text = 'a;b\r\n"x;y";"строка1\r\nстрока2"\r\n"с ""кавычкой""";1\r\n'
    df = read_csv_ru(text.encode("cp1251"))
    assert df["a"].tolist() == ["x;y", 'с "кавычкой"']
    assert df["b"].iloc[0] == "строка1\r\nстрока2"


def test_ragged_rows_headerless_duplicate_names_and_empty_input() -> None:
    df = read_csv_ru(b"a;a;\r\n1;2;3;4\r\n5;6\r\n")
    assert list(df.columns) == ["a", "a.1", "столбец", "столбец.1"] or list(df.columns)[:2] == ["a", "a.1"]
    assert df.attrs["ru"]["ragged_rows"] >= 1
    nohead = read_csv_ru(b"1;2\r\n3;4\r\n", header=False)
    assert list(nohead.columns) == ["столбец0", "столбец1"]
    assert len(nohead) == 2
    assert read_csv_ru(b"").empty
    assert read_csv_ru(b"\r\n\r\n").empty


def test_explicit_encoding_separator_and_decimal() -> None:
    df = read_csv_ru(b"x,y\n1.234,5.5\n", sep=",", encoding="utf-8")
    assert df["x"].tolist() == [1.234] and df["y"].tolist() == [5.5]
    df = read_csv_ru("x;y\n1,234;2\n3,500;4\n".encode("cp1251"), decimal=".")
    assert df["x"].tolist() == [1234.0, 3500.0], "точка задана десятичной, значит запятая — тысячи"


def test_write_defaults_match_russian_excel() -> None:
    df = pd.DataFrame(
        {
            "Дата": pd.to_datetime(["2024-01-05", "2024-02-06 10:30"], format="mixed"),
            "Сумма": [1234.5, -0.1],
            "Кол": [3, 12],
            "Имя": ["ООО «А»", "с;запятой"],
        }
    )
    out = to_csv_ru(df)
    assert out is not None
    text = out.decode("cp1251")
    assert text == 'Дата;Сумма;Кол;Имя\r\n05.01.2024 00:00:00;1234,5;3;ООО «А»\r\n06.02.2024 10:30:00;-0,1;12;"с;запятой"\r\n'


def test_write_date_only_when_no_times_and_utf8_bom_variant(tmp_path) -> None:  # type: ignore[no-untyped-def]
    df = pd.DataFrame({"Дата": pd.to_datetime(["2024-01-05", "2024-02-06"]), "Флаг": [True, False], "Пусто": [None, 1.5]})
    assert to_csv_ru(df) == "Дата;Флаг;Пусто\r\n05.01.2024;Да;\r\n06.02.2024;Нет;1,5\r\n".encode("cp1251")
    path = tmp_path / "x.csv"
    assert to_csv_ru(df, path, encoding="utf-8-sig") is None
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert read_csv_ru(path)["Дата"].tolist() == df["Дата"].tolist()
    assert to_csv_ru(df, date_format="%Y-%m-%d") == "Дата;Флаг;Пусто\r\n2024-01-05;Да;\r\n2024-02-06;Нет;1,5\r\n".encode("cp1251")


def test_write_rejects_characters_outside_the_encoding_with_context() -> None:
    df = pd.DataFrame({"a": ["ok", "плохо 😀"]})
    with pytest.raises(UnicodeEncodeError, match=r"не помещается в cp1251 \(строка 3"):
        to_csv_ru(df)
    assert to_csv_ru(df, errors="replace") == b"a\r\nok\r\n\xef\xe5\xeb\xef\xee \x3f\r\n".replace(b"\xef\xe5\xeb\xef\xee", "плохо".encode("cp1251"))


def test_accessor_methods() -> None:
    s = pd.Series(["1 234,5", "x"])
    n = s.ru.to_number()
    assert n.tolist()[0] == 1234.5 and pd.isna(n.iloc[1])
    assert pd.Series(["7707083893", "123", None]).ru.valid("inn").tolist() == [True, False, False]
    assert "контрольная цифра" in pd.Series(["7707083894"]).ru.problems("inn").iloc[0]
    assert pd.Series(["05.01.2024"]).ru.to_datetime().iloc[0] == pd.Timestamp("2024-01-05")
    with pytest.raises(ValueError, match="неизвестный вид"):
        s.ru.valid("nope")
    pd.DataFrame({"a": [1]}).ru.to_csv()
    assert ru.__version__


_WORDS = [
    "Иванов",
    "Петрова",
    "ООО",
    "Ромашка",
    "оплата",
    "счёт",
    "аванс",
    "возврат",
    "договор",
    "услуги",
    "товар",
    "Москва",
    "доставка",
    "Вектор",
    "за",
    "по",
    "март",
]
# осмысленные названия: слова из словаря и редкие «;», кавычки и «ёлочки»; бессмыслица из двух-трёх случайных букв определению кодировки не по зубам (см. README)
_names = st.builds(
    lambda words, deco: deco.format(" ".join(words)),
    st.lists(st.sampled_from(_WORDS), min_size=1, max_size=4),
    st.sampled_from(["{}", "{}", "«{}»", '"{}; доп."', "{}; {}".replace("{}; {}", "{}")]),
)


@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "дата": st.datetimes(min_value=datetime(1990, 1, 1), max_value=datetime(2060, 12, 31)).map(
                    lambda d: d.replace(hour=0, minute=0, second=0, microsecond=0)
                ),
                "сумма": st.integers(-(10**11), 10**11).map(lambda k: k / 100),
                "штук": st.integers(-1000, 10**9),
                "имя": _names,
            }
        ),
        min_size=2,
        max_size=15,
    )
)
@settings(max_examples=200, deadline=None)
def test_write_then_read_roundtrip_property(rows: list[dict[str, object]]) -> None:
    df = pd.DataFrame(rows)
    back = read_csv_ru(to_csv_ru(df) or b"")
    assert back["дата"].tolist() == df["дата"].tolist()
    assert back["сумма"].tolist() == df["сумма"].tolist()
    assert back["штук"].tolist() == df["штук"].tolist()
    assert back["имя"].tolist() == df["имя"].tolist()
    assert back.attrs["ru"]["encoding"].encoding == "cp1251" or back.attrs["ru"]["encoding"].encoding == "ascii"
