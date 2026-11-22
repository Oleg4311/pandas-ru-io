"""Сверка с независимой реализацией: проверки реквизитов в опубликованном npm-пакете @oleg4311/ru-kit (TypeScript) и здесь (Python)
написаны отдельно и должны давать одинаковые ответы на тысячах значений: верных, случайных и испорченных.

Тест ставит пакет из реестра npm во временный каталог. Без node и npm он пропускается, а в CI (переменная CI) отсутствие node считается ошибкой.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from pandas_ru_io import is_account, is_bik, is_inn, is_kpp, is_ogrn, is_ogrnip, is_snils

NODE = shutil.which("node")
NPM = shutil.which("npm")

SCRIPT = """
import { isInn, isSnils, isOgrn, isKpp, isBik, isBankAccount } from '@oleg4311/ru-kit';
import { readFileSync } from 'node:fs';
const d = JSON.parse(readFileSync(0, 'utf8'));
const out = {
  inn: d.inn.map(isInn), snils: d.snils.map(isSnils), ogrn: d.ogrn.map(isOgrn), kpp: d.kpp.map(isKpp), bik: d.bik.map(isBik),
  account: d.account.map(([a, b]) => isBankAccount(a, b)),
};
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def rukit(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if NODE is None or NPM is None:
        if os.environ.get("CI"):
            pytest.fail("в CI нужны node и npm для сверки с ru-kit")
        pytest.skip("нет node или npm")
    root = tmp_path_factory.mktemp("rukit")
    (root / "package.json").write_text('{"name":"x","private":true,"type":"module"}', encoding="utf-8")
    (root / "cross.mjs").write_text(SCRIPT, encoding="utf-8")
    proc = subprocess.run(
        [NPM, "install", "--no-audit", "--no-fund", "@oleg4311/ru-kit"], cwd=root, capture_output=True, text=True, shell=os.name == "nt", check=False
    )
    if proc.returncode != 0:
        if os.environ.get("CI"):
            pytest.fail(f"npm install не удался: {proc.stderr[-300:]}")
        pytest.skip(f"npm install не удался: {proc.stderr[-200:]}")
    return root


rnd = random.Random(99)


def digits(n: int) -> str:
    return "".join(rnd.choice("0123456789") for _ in range(n))


def with_noise(s: str) -> str:
    """Те же цифры с пробелами и дефисами в случайных местах, как их печатают в документах."""
    out = ""
    for ch in s:
        out += ch
        r = rnd.random()
        if r < 0.1:
            out += " "
        elif r < 0.15:
            out += "-"
    return out


def mutate(s: str) -> str:
    i = rnd.randrange(len(s))
    kind = rnd.randrange(3)
    if kind == 0:
        return s[:i] + str((int(s[i]) + rnd.randint(1, 9)) % 10) + s[i + 1 :] if s[i].isdigit() else s
    if kind == 1:
        return s[:i] + s[i + 1 :]
    return s[:i] + s[i] + s[i:]


def valid_number(kind: str) -> str:
    if kind == "inn10":
        p = digits(9)
        return next(p + str(c) for c in range(10) if is_inn(p + str(c)))
    if kind == "inn12":
        p = digits(10)
        return next(p + f"{c:02d}" for c in range(100) if is_inn(p + f"{c:02d}"))
    if kind == "snils":
        p = f"{rnd.randint(0, 999999999):09d}"
        return next(p + f"{c:02d}" for c in range(100) if is_snils(p + f"{c:02d}"))
    if kind == "ogrn":
        p = digits(12)
        return next(p + str(c) for c in range(10) if is_ogrn(p + str(c)))
    p = digits(14)
    return next(p + str(c) for c in range(10) if is_ogrnip(p + str(c)))


def sample(kind: str, n: int) -> list[str]:
    out: list[str] = []
    for i in range(n):
        v = valid_number(kind)
        out.append(with_noise(v) if i % 4 == 0 else v if i % 4 == 1 else mutate(v) if i % 4 == 2 else digits(len(v)))
    return out


def test_all_validators_agree_with_ru_kit(rukit: Path) -> None:
    n = 1500
    inn = sample("inn10", n) + sample("inn12", n)
    snils = sample("snils", n)
    ogrn = sample("ogrn", n) + sample("ogrnip", n)
    kpp = [digits(4) + rnd.choice([digits(2), "AB", "9Z", "a1", "A"]) + digits(3) for _ in range(n)]
    bik = [rnd.choice(["04", "04", "05", "14", "00"]) + digits(7) for _ in range(n)] + [digits(8), digits(10)]
    account: list[tuple[str, str]] = []
    for _ in range(n):
        b = (
            "04" + digits(4) + rnd.choice(["225", "601", "777", "003", "123", "999"])
        )  # окончания 000–002 толкуются в ru-kit и здесь по-разному (см. README)
        body, tail = digits(8), digits(11)
        key = next(k for k in range(10) if is_account(body + str(k) + tail, b))
        acc = body + str(key) + tail
        account.append((acc if rnd.random() < 0.5 else mutate(acc), b))
        acc301 = "301" + digits(5)
        key = next(k for k in range(10) if is_account(acc301 + str(k) + tail, b))
        account.append((acc301 + str(key) + tail, b))
    payload = {"inn": inn, "snils": snils, "ogrn": ogrn, "kpp": kpp, "bik": bik, "account": account}
    proc = subprocess.run([NODE or "node", "cross.mjs"], cwd=rukit, input=json.dumps(payload), capture_output=True, text=True, check=True)
    theirs = json.loads(proc.stdout)
    mine = {
        "inn": [is_inn(v) for v in inn],
        "snils": [is_snils(v) for v in snils],
        "ogrn": [is_ogrn(v) or is_ogrnip(v) for v in ogrn],
        "kpp": [is_kpp(v) for v in kpp],
        "bik": [is_bik(v) for v in bik],
        "account": [is_account(a, b) for a, b in account],
    }
    for kind, values in payload.items():
        diffs = [(v, m, t) for v, m, t in zip(values, mine[kind], theirs[kind], strict=True) if m != t]
        assert not diffs, f"{kind}: расхождений {len(diffs)} из {len(values)}, например {diffs[:3]}"
        valid = sum(mine[kind])
        assert 0.15 * len(values) < valid < 0.85 * len(values) or kind in {"kpp", "bik", "account"}, (
            f"{kind}: выборка вырождена ({valid} верных из {len(values)})"
        )
    assert sum(mine["account"]) > 300, "в выборке должны быть и верные счета"
    assert sum(mine["kpp"]) > 100 and sum(mine["bik"]) > 100
