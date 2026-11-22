"""Отчёт о разборе: что не удалось разобрать и что осталось неоднозначным. Данные молча не портятся."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParseReport:
    """Итог разбора одного столбца.

    `failed` — значения, которые не получилось разобрать (в результате на их месте пропуск);
    `ambiguous` — значения, разобранные по умолчанию, но допускающие другое прочтение (например, «1,234»);
    `empty` — пустые значения и прочерки, они не считаются ошибкой.
    """

    total: int = 0
    parsed: int = 0
    empty: int = 0
    failed: list[tuple[Any, str]] = field(default_factory=list)
    ambiguous: list[tuple[Any, str]] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Все непустые значения разобраны однозначно."""
        return not self.failed and not self.ambiguous

    def summary(self) -> str:
        parts = [f"всего {self.total}", f"разобрано {self.parsed}"]
        if self.empty:
            parts.append(f"пустых {self.empty}")
        if self.failed:
            parts.append(f"не разобрано {len(self.failed)}")
        if self.ambiguous:
            parts.append(f"неоднозначных {len(self.ambiguous)}")
        return ", ".join(parts)

    def __str__(self) -> str:
        return self.summary()
