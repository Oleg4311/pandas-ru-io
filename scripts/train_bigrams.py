"""Считает таблицу биграмм русских букв по scripts/train.txt и пишет src/pandas_ru_io/_bigrams.py.

Состояния: 33 строчные русские буквы, «S» (пробел, знаки, цифры, латиница, латиница: нейтральное) и «X» (всё остальное:
рамки cp866, греческие и прочие символы, которые появляются при неверной кодировке). Таблица хранит log P(следующее | предыдущее).
Запуск: python scripts/train_bigrams.py
"""

from __future__ import annotations

import math
from pathlib import Path

LETTERS = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
S, X = len(LETTERS), len(LETTERS) + 1
N = len(LETTERS) + 2
NEUTRAL_EXTRA = ""  # украинские и белорусские буквы нарочно НЕ нейтральны: при чтении cp1251 как cp866 русские «р…я» превращаются именно в них, и нейтральность делала такую ошибку дешёвой


def classify(ch: str) -> int:
    ch = ch.lower()
    i = LETTERS.find(ch)
    if i >= 0:
        return i
    if ch.isspace() or ch.isdigit() or ("a" <= ch <= "z") or ch in NEUTRAL_EXTRA:
        return S
    if ch.isascii() and ch.isprintable():
        return S  # знаки препинания и символы ASCII
    if ch in "«»—–−№…’‘“”„•·°×€₽ ":
        return S
    return X


def main() -> None:
    root = Path(__file__).resolve().parent
    text = (root / "train.txt").read_text(encoding="utf-8")
    counts = [[0.0] * N for _ in range(N)]
    prev = S
    for ch in text:
        cur = classify(ch)
        counts[prev][cur] += 1
        prev = cur
    table = []
    for row in counts:
        # X в обучении не встречается: даём ему маленькую, но не нулевую вероятность
        smoothed = [c + 0.5 for c in row[:X]] + [0.002]
        total = sum(smoothed)
        table.append([round(math.log(v / total), 3) for v in smoothed])
    out = [
        '"""Таблица log P(следующее | предыдущее) для русских букв. Создана scripts/train_bigrams.py, руками не правится."""',
        "",
        "from __future__ import annotations",
        "",
    ]
    out.append(f"LETTERS = {LETTERS!r}")
    out.append(f"NEUTRAL_EXTRA = {NEUTRAL_EXTRA!r}")
    out.append("TABLE: tuple[tuple[float, ...], ...] = (")
    for row in table:
        out.append("    (" + ", ".join(f"{v:.3f}" for v in row) + "),")
    out.append(")")
    (root.parent / "src" / "pandas_ru_io" / "_bigrams.py").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"обучено на {len(text)} знаках; таблица {N}x{N}")


if __name__ == "__main__":
    main()
