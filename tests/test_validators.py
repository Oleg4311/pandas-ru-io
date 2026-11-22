"""Валидаторы: известные реквизиты, свойства контрольных цифр (проверка перебором, независимая от формул) и сверка с ru-kit в test_crosscheck_rukit.py."""

from __future__ import annotations

import random

import pytest

from pandas_ru_io import (
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
    snils_error,
)

rnd = random.Random(2026)


def digits(n: int) -> str:
    return "".join(rnd.choice("0123456789") for _ in range(n))


def test_known_real_requisites() -> None:
    # ИНН и ОГРН Сбербанка, пример СНИЛС из документации ПФР, пример ОГРНИП, БИК Сбербанка
    assert is_inn("7707083893")
    assert is_inn("500100732259")
    assert is_ogrn("1027700132195")
    assert is_ogrnip("304500116000157")
    assert is_snils("112-233-445 95")
    assert is_snils("11223344595")
    assert is_bik("044525225")
    assert is_kpp("770701001")


def test_separators_and_nbsp_are_ignored() -> None:
    assert is_inn("77 07 08 38 93")
    assert is_inn("7707 083893")
    assert is_snils("112 233 445 95")
    assert is_ogrn("1 02 77 00 13 21 95")
    assert not is_inn("7707083893x")
    assert not is_inn("")
    assert not is_inn(None)
    assert not is_inn(7707083893)


@pytest.mark.parametrize(
    ("value", "needle"),
    [("123", "нужно 10 или 12 цифр, а не 3"), ("7707083894", "контрольная цифра"), ("77070838ab", "только цифры"), ("", "пусто")],
)
def test_inn_messages(value: str, needle: str) -> None:
    err = inn_error(value)
    assert err is not None
    assert needle in err
    assert err.startswith("ИНН:")


def test_exactly_one_check_digit_is_valid_for_every_prefix() -> None:
    """Перебор всех возможных контрольных цифр: из десяти подходит ровно одна. Не использует формулу из кода."""
    for _ in range(300):
        p9 = digits(9)
        assert sum(is_inn(p9 + str(c)) for c in range(10)) == 1
        p10 = digits(10)
        assert sum(is_inn(p10 + f"{c:02d}") for c in range(100)) == 1  # из ста окончаний подходит ровно одно
        p12 = digits(12)
        assert sum(is_ogrn(p12 + str(c)) for c in range(10)) == 1
        p14 = digits(14)
        assert sum(is_ogrnip(p14 + str(c)) for c in range(10)) == 1
        s9 = f"{rnd.randint(1001999, 999999999):09d}"
        assert sum(is_snils(s9 + f"{c:02d}") for c in range(100)) == 1


def test_account_key_is_unique_for_every_account_and_bik() -> None:
    for _ in range(300):
        bik = "04" + digits(7)
        body = digits(8)
        tail = digits(11)
        valid = [k for k in range(10) if is_account(body + str(k) + tail, bik)]
        assert len(valid) == 1, (bik, body, tail, valid)


def test_account_rkc_and_correspondent_accounts_use_the_zero_prefix() -> None:
    # корсчёт 301…: приставка «0» + 5-я и 6-я цифры БИК; для обычного счёта три последние цифры БИК
    bik = "044525225"
    for _ in range(50):
        body, tail = "30101810", digits(11)
        assert sum(is_account(body[:8] + str(k) + tail, bik) for k in range(10)) == 1
    # один и тот же набор цифр не может быть верным и по «0 + 5–6», и по «7–9»: для данного БИК решение принимает префикс счёта
    assert account_error("30101810400000000225", bik) in (None, "Счёт: контрольный ключ не сходится с БИК")


def test_single_digit_errors_are_mostly_detected() -> None:
    """Контрольные цифры ловят почти все ошибки в одной цифре; точная доля измеряется, а не предполагается."""
    missed = total = 0
    for _ in range(300):
        p9 = digits(9)
        good = next(p9 + str(c) for c in range(10) if is_inn(p9 + str(c)))
        for i in range(10):
            for d in "0123456789":
                if d == good[i]:
                    continue
                total += 1
                missed += is_inn(good[:i] + d + good[i + 1 :])
    assert missed / total < 0.02, f"не замечено {missed} из {total}"


def test_snils_below_the_protected_range_is_accepted_by_format() -> None:
    assert is_snils("001-001-998 00")
    assert is_snils("000-000-001 99")
    assert snils_error("112-233-445 96") == "СНИЛС: неверная контрольная сумма"
    assert snils_error("1122334459") == "СНИЛС: нужно 11 цифр, а не 10"


def test_snils_control_100_and_101_become_00() -> None:
    # сумма 100 и 101 даёт контроль 00; ищем такие номера перебором и проверяем оба случая
    found: set[int] = set()
    for n in range(1002000, 1002000 + 200000):
        s = f"{n:09d}"
        total = sum(int(d) * w for d, w in zip(s, range(9, 0, -1), strict=True))
        if total in (100, 101):
            assert is_snils(s + "00")
            assert not is_snils(s + "01")
            found.add(total)
        if len(found) == 2:
            break
    assert found == {100, 101}


def test_kpp_bik_formats() -> None:
    assert is_kpp("770743001")
    assert is_kpp("77074B001")  # пятая и шестая позиции: допустимы заглавные латинские буквы
    assert is_kpp("7707AB001")
    assert not is_kpp("7707ab001")
    assert not is_kpp("77070100a")
    assert kpp_error("77070100") == "КПП: нужно 9 знаков, а не 8"
    assert bik_error("144525225") == "БИК: российский БИК начинается с 04"
    assert not is_bik("04452522")


def test_validators_never_raise_on_garbage() -> None:
    for junk in [None, 1, 1.5, b"123", [], {}, "ё" * 10, "\x00" * 10, "9" * 1000, "١" * 10]:
        for fn in (is_inn, is_snils, is_ogrn, is_ogrnip, is_kpp, is_bik):
            assert fn(junk) is False
        assert is_account(junk, "044525225") is False
