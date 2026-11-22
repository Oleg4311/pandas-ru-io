"""Собирает корпус русских текстов из README и документации проектов в соседних каталогах.

Проекты делятся на обучающие (по ним считается таблица биграмм) и отложенные (по ним проверяется определение кодировки):
так проверка идёт на текстах, которых модель не видела, и фразы из одного README не утекают в тест.
Использование: python scripts/collect_corpus.py ПАПКА_С_ПРОЕКТАМИ
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HOLDOUT = {"agentsmd-lint", "plan-postcard", "migration-rehearsal", "byo-regex-engine", "contract-impact-board"}
SKIP = {"node_modules", ".venv", "target", ".git", "dist", "site", "__pycache__"}


def russian_paragraphs(text: str) -> list[str]:
    out = []
    for block in re.split(r"\n\s*\n", text):
        block = re.sub(r"```.*?```", " ", block, flags=re.S)  # код не нужен
        block = re.sub(r"`[^`]*`|\[([^\]]*)\]\([^)]*\)|[#>*|_]+", lambda m: m.group(1) or " ", block)
        block = re.sub(r"\s+", " ", block).strip()
        letters = sum(1 for c in block if "а" <= c.lower() <= "я" or c in "ёЁ")
        if len(block) >= 60 and letters / len(block) > 0.55:
            out.append(block)
    return out


def main(root: Path) -> None:
    train: list[str] = []
    test: list[str] = []
    for project in sorted(p for p in root.glob("*/*") if p.is_dir() and not (SKIP & set(p.parts))):
        target = test if project.name in HOLDOUT else train
        for md in sorted(project.rglob("*.md")):
            if SKIP & set(md.relative_to(project).parts) or md.name in {"CHANGELOG.md", "LICENSE.md"}:
                continue
            target.extend(russian_paragraphs(md.read_text(encoding="utf-8", errors="ignore")))
    here = Path(__file__).resolve().parent.parent
    (here / "tests" / "corpus").mkdir(parents=True, exist_ok=True)
    (here / "scripts" / "train.txt").write_text("\n".join(train), encoding="utf-8")
    (here / "tests" / "corpus" / "holdout.txt").write_text("\n".join(test), encoding="utf-8")
    print(f"обучающих абзацев {len(train)} ({sum(map(len, train))} знаков), отложенных {len(test)} ({sum(map(len, test))} знаков)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
