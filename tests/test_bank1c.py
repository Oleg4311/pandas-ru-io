from __future__ import annotations

import random
from datetime import datetime

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pandas_ru_io import is_account, is_inn, read_1c, validate_statement, write_1c

SAMPLE = """1CClientBankExchange
ВерсияФормата=1.03
Кодировка=Windows
Отправитель=Банк
ДатаСоздания=31.01.2024
ДатаНачала=01.01.2024
ДатаКонца=31.01.2024
РасчСчет=40702810400000000001
Документ=Платежное поручение
СекцияРасчСчет
ДатаНачала=01.01.2024
ДатаКонца=31.01.2024
РасчСчет=40702810400000000001
НачальныйОстаток=1000.00
КонечныйОстаток=2500.50
КонецРасчСчет
СекцияДокумент=Платежное поручение
Номер=15
Дата=15.01.2024
Сумма=1500.50
ПлательщикСчет=40702810400000000001
Плательщик=ООО «Ромашка»
ПлательщикИНН=7707083893
ПолучательСчет=40702810500000000002
Получатель=ИП Иванов Иван Иванович
ПолучательИНН=500100732259
НазначениеПлатежа=Оплата по счёту № 15 от 10.01.2024, в т.ч. НДС 20%
КонецДокумента
СекцияДокумент=Платежное поручение
Номер=16
Дата=16.01.2024
Сумма=1 000,00
КонецДокумента
КонецФайла
"""


def test_reads_a_typical_statement_in_cp1251() -> None:
    st_ = read_1c(SAMPLE.replace("\n", "\r\n").encode("cp1251"))
    assert st_.encoding is not None
    assert st_.encoding.encoding == "cp1251"
    assert st_.header["ВерсияФормата"] == "1.03"
    assert st_.accounts[0]["КонечныйОстаток"] == "2500.50"
    d = st_.documents
    assert len(d) == 2
    assert d["Сумма"].tolist() == [1500.5, 1000.0]
    assert d["Дата"].tolist() == [pd.Timestamp("2024-01-15"), pd.Timestamp("2024-01-16")]
    assert d.loc[0, "НазначениеПлатежа"] == "Оплата по счёту № 15 от 10.01.2024, в т.ч. НДС 20%"
    assert d.loc[0, "Плательщик"] == "ООО «Ромашка»"
    assert st_.warnings == []


def test_reads_str_bytes_path_and_file_object(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "выписка.txt"
    path.write_bytes(SAMPLE.encode("cp1251"))
    for src in (path, str(path), SAMPLE.encode("cp1251"), SAMPLE, open(path, "rb")):  # noqa: SIM115
        assert len(read_1c(src).documents) == 2


def test_repeated_header_keys_become_lists_and_unknown_lines_warn() -> None:
    text = "1CClientBankExchange\nДокумент=А\nДокумент=Б\nмусор без равно\nКонецФайла\n"
    st_ = read_1c(text)
    assert st_.header["Документ"] == ["А", "Б"]
    assert any("нет знака" in w for w in st_.warnings)
    assert st_.documents.empty


def test_truncated_file_is_reported_not_silently_accepted() -> None:
    st_ = read_1c(SAMPLE.split("СекцияДокумент=Платежное поручение\nНомер=16")[0])
    assert len(st_.documents) == 1
    assert any("КонецФайла" in w for w in st_.warnings)
    cut = read_1c("1CClientBankExchange\nСекцияДокумент=Платежное поручение\nНомер=1\n")
    assert any("оборван посреди секции" in w for w in cut.warnings)


def test_not_a_1c_file_is_rejected() -> None:
    with pytest.raises(ValueError, match="1CClientBankExchange"):
        read_1c("Номер;Сумма\n1;2\n")
    with pytest.raises(ValueError):
        read_1c("")


def test_write_then_read_gives_the_same_documents() -> None:
    docs = read_1c(SAMPLE).documents
    data = write_1c(docs, header={"Отправитель": "Тест"}, accounts=[{"РасчСчет": "40702810400000000001"}])
    assert data.startswith(b"1CClientBankExchange\r\n")
    assert data.endswith(b"\xca\xee\xed\xe5\xf6\xd4\xe0\xe9\xeb\xe0\r\n")  # «КонецФайла» в cp1251
    back = read_1c(data)
    assert back.header["Отправитель"] == "Тест"
    assert back.accounts == [{"РасчСчет": "40702810400000000001"}]
    pd.testing.assert_frame_equal(back.documents[docs.columns], docs, check_dtype=False)


def test_write_rejects_characters_outside_cp1251_with_a_location() -> None:
    df = pd.DataFrame({"Номер": ["1"], "НазначениеПлатежа": ["Оплата 😀"], "Сумма": [1.0]})
    with pytest.raises(UnicodeEncodeError, match="не помещается в cp1251"):
        write_1c(df)


_text = st.text(alphabet="абвгдеёжзийклмнопрстуфхцчшщъыьэюя ABCabc0123456789.,-«»№", min_size=1, max_size=30).map(str.strip).filter(bool)


@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "Номер": st.integers(1, 99999).map(str),
                "Дата": st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2040, 12, 31)).map(
                    lambda d: d.replace(hour=0, minute=0, second=0, microsecond=0)
                ),
                "Сумма": st.integers(1, 10**12).map(lambda k: k / 100),
                "НазначениеПлатежа": _text,
            }
        ),
        min_size=1,
        max_size=8,
    )
)
@settings(max_examples=150, deadline=None)
def test_roundtrip_property(rows: list[dict[str, object]]) -> None:
    df = pd.DataFrame(rows)
    df["ТипДокумента"] = "Платежное поручение"
    df = df[["ТипДокумента", "Номер", "Дата", "Сумма", "НазначениеПлатежа"]]
    back = read_1c(write_1c(df)).documents
    assert back["Номер"].tolist() == df["Номер"].tolist()
    assert [pd.Timestamp(x) for x in back["Дата"]] == [pd.Timestamp(x) for x in df["Дата"]]
    assert back["Сумма"].tolist() == df["Сумма"].tolist()
    assert back["НазначениеПлатежа"].tolist() == df["НазначениеПлатежа"].tolist()


def test_validate_statement_finds_bad_inn_account_bik_and_amount() -> None:
    rnd = random.Random(1)
    bik = "044525225"
    body, tail = "40702810", "".join(rnd.choice("0123456789") for _ in range(11))
    good = next(body + str(k) + tail for k in range(10) if is_account(body + str(k) + tail, bik))
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    df = pd.DataFrame(
        {
            "Сумма": [100.0, -5.0, float("nan"), 10.0],
            "ПлательщикИНН": ["7707083893", "7707083894", "", "123"],
            "ПлательщикБИК": [bik, bik, "", "144525225"],
            "ПлательщикРасчСчет": [good, bad, "", good],
            "ПолучательКПП": ["770701001", "", "", "77070100"],
        }
    )
    issues = validate_statement(df)
    got = {(r.строка, r.поле) for r in issues.itertuples()}
    assert got == {
        (1, "ПлательщикИНН"),
        (1, "ПлательщикРасчСчет"),
        (1, "Сумма"),
        (2, "Сумма"),
        (3, "ПлательщикИНН"),
        (3, "ПлательщикБИК"),
        (3, "ПолучательКПП"),
    }
    assert is_inn("7707083893")
    assert validate_statement(df.iloc[[0]]).empty
    assert list(issues.columns) == ["строка", "поле", "значение", "замечание"]
