"""Определение кодировки. Модель обучена на русской документации (scripts/train.txt); проверяется на отложенных текстах (tests/corpus),
которых при обучении не было, и на табличных строках другого жанра. Результат сравнивается с charset-normalizer."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pandas_ru_io import decode_bytes, detect_encoding

CORPUS = Path(__file__).parent / "corpus"
HOLDOUT = [p for p in (CORPUS / "holdout.txt").read_text(encoding="utf-8").split("\n") if p]
TABLE = [p for p in (CORPUS / "table_like.txt").read_text(encoding="utf-8").split("\n") if p]
ENCODINGS = ["cp1251", "cp866", "koi8-r", "utf-8"]


def chunks(source: list[str], length: int, n: int, seed: int) -> list[str]:
    rnd = random.Random(seed)
    out = []
    pool = [p for p in source if len(p) >= length]
    while len(out) < n:
        p = rnd.choice(pool)
        start = rnd.randrange(0, len(p) - length + 1)
        out.append(p[start : start + length])
    return out


def accuracy(texts: list[str], seed: int) -> tuple[float, list[tuple[str, str, float]]]:
    rnd = random.Random(seed)
    ok = 0
    errors = []
    for t in texts:
        enc = rnd.choice(ENCODINGS)
        guess = detect_encoding(t.encode(enc, errors="replace"))
        if guess.encoding == enc or (guess.encoding == "ascii"):
            ok += 1
        else:
            errors.append((enc, guess.encoding, guess.confidence))
    return ok / len(texts), errors


@pytest.mark.parametrize(("length", "minimum"), [(20, 0.97), (40, 0.99), (100, 0.995), (300, 0.995)])
def test_accuracy_on_heldout_prose_by_length(length: int, minimum: float) -> None:
    acc, errors = accuracy(chunks(HOLDOUT, length, 500, seed=length), seed=1)
    assert acc >= minimum, f"точность {acc:.3f} при длине {length}; ошибки {errors[:5]}"


@pytest.mark.parametrize(("cells", "minimum"), [(1, 0.99), (5, 0.995), (30, 0.999)])
def test_accuracy_on_table_like_strings(cells: int, minimum: float) -> None:
    rnd = random.Random(cells)
    texts = [";".join(rnd.sample(TABLE, cells)) for _ in range(400)]
    acc, errors = accuracy(texts, seed=2)
    assert acc >= minimum, f"точность {acc:.3f} для {cells} ячеек; ошибки {errors[:5]}"


def test_confidence_is_calibrated_confident_answers_are_right() -> None:
    """Если уверенность от 0,95, ошибок быть не должно: на коротких строках модель честно сомневается, а не врёт."""
    rnd = random.Random(5)
    confident = wrong = 0
    for _ in range(3000):
        if rnd.random() < 0.5:
            text = ";".join(rnd.sample(TABLE, rnd.choice([1, 1, 2, 3])))
        else:
            text = chunks(HOLDOUT, rnd.choice([10, 15, 20, 30, 50]), 1, seed=rnd.randrange(10**6))[0]
        enc = rnd.choice(["cp1251", "cp866", "koi8-r"])
        g = detect_encoding(text.encode(enc, errors="replace"))
        if g.encoding != "ascii" and g.confidence >= 0.95:
            confident += 1
            wrong += g.encoding != enc
    assert confident > 2000
    assert wrong / confident < 0.002, f"уверенных ошибок {wrong} из {confident}"


def test_beats_charset_normalizer_on_russian_cells() -> None:
    cn = pytest.importorskip("charset_normalizer")
    rnd = random.Random(11)
    mine = theirs = 0
    n = 300
    for _ in range(n):
        text = ";".join(rnd.sample(TABLE, 3))
        enc = rnd.choice(["cp1251", "cp866", "koi8-r"])
        data = text.encode(enc, errors="replace")
        mine += detect_encoding(data).encoding == enc
        best = cn.from_bytes(data).best()
        norm = {
            "windows-1251": "cp1251",
            "cp1125": "cp866",
            "koi8-u": "koi8-r",
            "ibm866": "cp866",
            "koi8-r": "koi8-r",
            "cp1251": "cp1251",
            "cp866": "cp866",
        }
        theirs += best is not None and norm.get(best.encoding.lower().replace("_", "-"), best.encoding) == enc
    # charset-normalizer рассчитан на сотни кодировок и любые языки; здесь выбор из трёх русских кодировок, поэтому узкая модель выигрывает
    assert mine / n >= 0.99
    assert mine > theirs


def test_boms_ascii_empty_and_utf8() -> None:
    assert detect_encoding(b"").encoding == "utf-8"
    assert detect_encoding(b"just ascii; 1,5").encoding == "ascii"
    assert detect_encoding("﻿Да".encode()).encoding == "utf-8-sig"
    assert detect_encoding("Да".encode("utf-16")).encoding == "utf-16"
    assert detect_encoding("Да".encode("utf-32")).encoding == "utf-32"
    g = detect_encoding("Привет, мир".encode())
    assert (g.encoding, g.confidence) == ("utf-8", pytest.approx(1.0, abs=0.01))


def test_utf16_without_bom() -> None:
    text = "Оплата по счёту № 15 от 05.01.2024"
    assert detect_encoding(text.encode("utf-16-le")).encoding == "utf-16-le"
    assert detect_encoding(text.encode("utf-16-be")).encoding == "utf-16-be"


def test_very_short_strings_are_honestly_uncertain() -> None:
    low = [detect_encoding(w.encode("cp1251")).confidence for w in ["да", "нет", "ок", "и"]]
    assert max(low) < 0.97, "двух-трёх букв недостаточно, чтобы быть уверенным"


def test_decode_bytes_uses_fallback_below_threshold_and_explicit_encoding() -> None:
    text, guess = decode_bytes("да".encode("cp866"), fallback="cp1251", min_confidence=0.999)
    assert guess.encoding == "cp1251"
    assert "ниже порога" in guess.reason
    text, guess = decode_bytes("Привет".encode("koi8-r"), encoding="koi8-r")
    assert text == "Привет"
    assert guess.reason == "задана явно"
    text, _ = decode_bytes("﻿Привет".encode())
    assert text == "Привет", "BOM не остаётся в тексте"
    text, _ = decode_bytes("Оплата по счёту № 15, сумма 1 234,56 руб.".encode("cp1251"))
    assert text == "Оплата по счёту № 15, сумма 1 234,56 руб."


@given(st.binary(max_size=300))
@settings(max_examples=300)
def test_arbitrary_bytes_never_raise(data: bytes) -> None:
    g = detect_encoding(data)
    assert 0.0 <= g.confidence <= 1.0
    decode_bytes(data)  # не падает на любых байтах


def test_cp1251_with_the_undefined_byte_is_still_detected() -> None:
    data = "Платёж № 5, сумма 100 руб.".encode("cp1251") + b"\x98"  # 0x98 в cp1251 не определён
    assert detect_encoding(data).encoding == "cp1251"
    text, _ = decode_bytes(data)
    assert text.startswith("Платёж")


def test_regression_cp1251_read_as_cp866_is_not_plausible() -> None:
    """Найдено property-тестом: украинские буквы раньше считались «нейтральными», и cp1251, прочитанная как cp866 («фрЄр ёєььр»), оценивалась правдоподобной."""
    data = 'дата;сумма;штук;имя\r\n01.01.2000;0;0;";бф"\r\n'.encode("cp1251")
    g = detect_encoding(data)
    assert g.encoding == "cp1251"
    assert g.confidence > 0.95
    assert g.scores["cp866"] < g.scores["cp1251"] - 30
