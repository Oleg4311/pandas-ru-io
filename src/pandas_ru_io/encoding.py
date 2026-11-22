"""Определение кодировки русского текста: UTF-8/16/32 (по BOM и строгому разбору), cp1251, cp866, KOI8-R (по биграммам букв)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ._bigrams import LETTERS, NEUTRAL_EXTRA, TABLE

__all__ = ["SINGLE_BYTE", "EncodingGuess", "decode_bytes", "detect_encoding", "score_text"]

SINGLE_BYTE = ("cp1251", "cp866", "koi8-r")
#: Температура softmax: модель слишком самоуверенна (соседние буквы в тексте не независимы), поэтому разности правдоподобий делятся на неё.
#: Значение подобрано на отложенных текстах: при уверенности от 0,95 ошибок не было ни на документации, ни на табличных строках.
TEMPERATURE = 3.0
_S = len(LETTERS)
_X = len(LETTERS) + 1
_LOOKUP = {ch: i for i, ch in enumerate(LETTERS)}
_PUNCT_EXTRA = set("«»—–−№…’‘“”„•·°×€₽ ")
_BOMS = (
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)


@dataclass(frozen=True)
class EncodingGuess:
    """Догадка о кодировке.

    `confidence` — вероятность выбранной кодировки среди проверенных при равных априорных вероятностях: растёт с длиной текста.
    Для коротких строк (меньше десятка слов) уверенность честно низкая: cp1251 и KOI8-R различаются слабее, чем кажется.
    """

    encoding: str
    confidence: float
    scores: dict[str, float] = field(default_factory=dict)
    reason: str = ""


def _classify(ch: str) -> int:
    ch = ch.lower()
    i = _LOOKUP.get(ch)
    if i is not None:
        return i
    if ch.isspace():
        return _S if ch in "\t\n\r  " else _X
    if ch.isdigit() or ("a" <= ch <= "z") or ch in NEUTRAL_EXTRA or ch in _PUNCT_EXTRA:
        return _S
    if ch.isascii():
        return _S if ch.isprintable() else _X
    return _X


def score_text(text: str) -> tuple[float, int]:
    """Суммарное log-правдоподобие текста как русского и число переходов."""
    prev = _S
    total = 0.0
    n = 0
    for ch in text:
        cur = _classify(ch)
        total += TABLE[prev][cur]
        prev = cur
        n += 1
    return total, n


def _decode(data: bytes, encoding: str) -> str | None:
    try:
        return data.decode(encoding)
    except UnicodeDecodeError:
        return None


def _rank(data: bytes, candidates: list[str]) -> tuple[str, float, dict[str, float]]:
    """Выбирает лучшую кодировку из списка и считает вероятность по разнице правдоподобий."""
    scores: dict[str, float] = {}
    for enc in candidates:
        text = _decode(data, enc)
        if text is None:
            text = data.decode(enc, errors="replace")  # cp1251: один байт не определён; такие тексты не отбрасываем, а штрафуем
        scores[enc], _ = score_text(text)
    ordered = sorted(scores, key=lambda e: scores[e], reverse=True)
    best = ordered[0]
    if len(ordered) == 1:
        return best, 1.0, scores
    # доля лучшей модели среди всех при равных априорных вероятностях (softmax по суммарному правдоподобию)
    denom = sum(math.exp(max((scores[e] - scores[best]) / TEMPERATURE, -50.0)) for e in ordered)
    return best, 1.0 / denom, scores


def detect_encoding(data: bytes, *, candidates: tuple[str, ...] = SINGLE_BYTE) -> EncodingGuess:
    """Определяет кодировку байтов. Порядок проверок: BOM, UTF-16 без BOM, чистый ASCII, строгий UTF-8, затем биграммы.

    В `candidates` перечисляются однобайтные кодировки, между которыми выбирает модель.
    """
    for bom, name in _BOMS:
        if data.startswith(bom):
            return EncodingGuess(name, 1.0, reason="метка порядка байтов (BOM)")
    if not data:
        return EncodingGuess("utf-8", 1.0, reason="пусто")
    # UTF-16 без BOM: у латиницы старший байт 0x00, у кириллицы (U+0400–04FF) 0x04; в одной из двух позиций они почти везде
    if len(data) >= 4 and len(data) % 2 == 0:
        le = sum(b in (0, 4) for b in data[1::2]) / (len(data) // 2)
        be = sum(b in (0, 4) for b in data[0::2]) / (len(data) // 2)
        if max(le, be) >= 0.9 and min(le, be) < 0.5:
            enc = "utf-16-le" if le > be else "utf-16-be"
            if _decode(data, enc) is not None:
                return EncodingGuess(enc, 0.95, reason="старшие байты 0x00 или 0x04 в одной позиции: UTF-16 без BOM")
    if all(b < 0x80 for b in data):
        return EncodingGuess("ascii", 1.0, reason="только ASCII: подходит любая кодировка")
    utf8 = _decode(data, "utf-8")
    cands = list(candidates)
    if utf8 is not None:
        cands = ["utf-8", *cands]
    best, conf, scores = _rank(data, cands)
    reason = "биграммы русских букв"
    if utf8 is not None and best != "utf-8":
        reason += " (текст также является корректным UTF-8)"
    return EncodingGuess(best, conf, scores, reason)


def decode_bytes(
    data: bytes,
    *,
    encoding: str | None = None,
    fallback: str = "cp1251",
    min_confidence: float = 0.95,
) -> tuple[str, EncodingGuess]:
    """Декодирует байты. Без `encoding` кодировка определяется; при уверенности ниже `min_confidence` берётся `fallback`.

    Порог 0,95 выбран по проверке на отложенных текстах: при такой уверенности ошибок не было, а на 0,8–0,95 они встречались.
    Если короткий текст не в cp1251 и модель сомневается, укажите `encoding` явно.
    """
    if encoding is not None:
        text = data.decode(encoding)
        return text.removeprefix("﻿"), EncodingGuess(encoding, 1.0, reason="задана явно")
    guess = detect_encoding(data)
    enc = {"ascii": "utf-8"}.get(guess.encoding, guess.encoding)
    if guess.confidence < min_confidence:
        enc = fallback
        guess = EncodingGuess(fallback, guess.confidence, guess.scores, f"уверенность {guess.confidence:.2f} ниже порога: взят {fallback}")
    text = data.decode(enc, errors="replace")
    return text.removeprefix("﻿"), guess
