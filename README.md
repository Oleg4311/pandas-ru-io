# pandas-ru-io

[![CI](https://github.com/Oleg4311/pandas-ru-io/actions/workflows/ci.yml/badge.svg)](https://github.com/Oleg4311/pandas-ru-io/actions/workflows/ci.yml)
[Релизы](https://github.com/Oleg4311/pandas-ru-io/releases) · [Точность определения кодировки](docs/encoding-eval.md)

**Русские табличные данные в pandas без боли.** Открыли CSV из русского Excel, а там кракозябры, запятые в дробях, даты «05.01.2024» и ИНН без ведущих нулей? Библиотека сама определяет кодировку (cp1251, cp866, KOI8-R, UTF), разделитель, читает числа «1 234,56» и «(500,00)», даты «5 января 2024 г.», **не ломает коды** (ИНН, счета, значения с ведущим нулём), читает и пишет выписки банка в формате **1С** и проверяет реквизиты по контрольным цифрам. Ничего не портится молча: непонятные ячейки превращаются в пропуск и попадают в отчёт.

*English: pandas I/O for Russian tabular data — encoding detection (cp1251/cp866/KOI8-R/UTF), Russian number and date formats, 1C bank-statement files, INN/SNILS/OGRN/BIK/account validation by check digits. Every parse returns a report instead of silently coercing. See the [English section](#english).*

```python
import pandas as pd
import pandas_ru_io as ru

df = ru.read_csv_ru("выписка.csv")  # кодировка, разделитель, числа, даты и коды определяются сами
df.attrs["ru"]["columns"]["Сумма"]  # {'kind': 'number', 'reason': ..., 'report': ParseReport(...)}
df["Дата"].ru.to_datetime(errors="raise")  # или s.ru.to_number(), s.ru.valid("inn")
df.ru.to_csv("для_excel.csv")  # cp1251, «;», запятая в дробях, даты «дд.мм.гггг»
```

## Что умеет

| Возможность | Пример | Как |
|---|---|---|
| **Кодировка** | байты из cp866 → правильный текст | биграммы русских букв между cp1251, cp866, KOI8-R, UTF-8/16/32 (BOM, строгий UTF-8); уверенность в процентах, [измерена](docs/encoding-eval.md) |
| **Разделитель** | `;`, табуляция, `,`, `\|` | по тому, какой даёт одинаковое число столбцов; кавычки и переносы внутри ячеек понимает |
| **Числа** | `1 234,56`, `(500,00)`, `12,5 руб.`, `1.234,56`, `−5,5` | пробелы, NBSP и узкий пробел как тысячи; скобки и знаки минуса; валюта; десятичный разделитель столбца определяется по однозначным значениям; «1,234» без подсказок остаётся в `report.ambiguous` |
| **Даты** | `05.01.2024`, `5 января 2024 г.`, `05.01.24 10:30`, ISO, `20240105`, серийные числа Excel | день-месяц-год всегда; 31.02 это ошибка, а не «март»; двузначный год как в `%y` |
| **Коды не портятся** | ИНН `0012345678`, счёт из 20 цифр | столбцы с ведущим нулём, длинными числами или названием «ИНН/счёт/БИК…» остаются строками |
| **Выписки 1С** | `1CClientBankExchange` | `read_1c` и `write_1c` (cp1251, CRLF), `validate_statement` проверяет реквизиты документов |
| **Реквизиты** | `is_inn`, `is_snils`, `is_ogrn`, `is_ogrnip`, `is_kpp`, `is_bik`, `is_account(счёт, бик)` | контрольные цифры и ключ счёта по БИК; `*_error` возвращает причину по-русски |
| **Запись для Excel** | `to_csv_ru` | cp1251 или utf-8-sig, `;`, запятая в дробях, `дд.мм.гггг`; символ вне кодировки даёт ошибку с номером строки |

## Отчёты вместо тихих потерь

```python
nums = ru.to_number(pd.Series(["10", "abc", "", "2,5"]))
nums.attrs["ru_report"]  # всего 4, разобрано 2, пустых 1, не разобрано 1
nums.attrs["ru_report"].failed  # [(1, 'abc')]
ru.to_number(s, errors="raise")  # ValueError: не число: 'abc' (строка 1)
```

## Что проверено

- **Контрольные цифры сверены с независимой реализацией.** Проверки ИНН, СНИЛС, ОГРН, КПП, БИК и расчётных счетов написаны здесь на Python и отдельно в опубликованном npm-пакете [`@oleg4311/ru-kit`](https://www.npmjs.com/package/@oleg4311/ru-kit) на TypeScript. Тест ставит пакет из реестра и сравнивает ответы на **13 тысячах значений** (верных, случайных, испорченных, с пробелами и дефисами): расхождений нет. Кроме того, контрольные цифры проверены перебором: для любого префикса подходит ровно одна цифра (для ИНН-12 ровно одно из ста окончаний), а известные реквизиты (Сбербанк, пример СНИЛС) проходят.
- **Кодировки на отложенных текстах:** модель обучена на документации одних проектов и проверена на абзацах других, плюс на табличных строках другого жанра. От 20 знаков ошибок не найдено ни в одном из 400 образцов на каждую длину; на коротких строках (до 80 знаков) универсальный `charset-normalizer` заметно слабее, на длинных так же точен ([таблица](docs/encoding-eval.md)). Уверенность откалибрована: при значении от 0,95 уверенных ошибок не было, поэтому ниже этого порога берётся запасная cp1251.
- **Property-тесты нашли ошибку модели:** украинские буквы считались «нейтральными», и cp1251, прочитанная как cp866 («фрЄр ёєььр»), выглядела правдоподобной для короткого заголовка. После исправления это зафиксировано отдельным тестом.
- **Round-trip:** запись и чтение CSV и файлов 1С возвращают те же значения (hypothesis: даты, суммы с копейками, целые, русский текст с `;`, кавычками и «»); число ↔ текст ↔ число без потерь на сотнях случайных значений.
- **Даты:** каждая форма названия месяца, невозможные даты (31.02, 29.02.2023), серийные числа Excel (в том числе несуществующее 29.02.1900).
- **Мутации:** 11 поломок (вес в ИНН, формула ОГРНИП, префикс корсчёта, неоднозначные числа, год-стержень, граница Excel, ведущий ноль, обрыв файла 1С, температура уверенности, порог, нейтральные буквы) тесты ловят.
- 148 тестов; `ruff`, `mypy --strict`; CI на Python 3.10–3.13 и pandas 2.x и 3.x, Linux и Windows.

## Честные ограничения

- **Кодировка угадывается, а не знается.** Выбор идёт между cp1251, cp866, KOI8-R и UTF; ISO-8859-5, MacCyrillic и другие не рассматриваются. Для одного-двух слов уверенность низкая (около 0,6), поэтому берётся cp1251. Проверка шла на технической прозе и сгенерированных строках; на настоящих выгрузках точность может быть ниже. Если знаете кодировку, передайте `encoding=`.
- **Обучающие тексты:** таблица биграмм посчитана на русской документации проектов автора (в репозитории только таблица и скрипт, текст обучения не публикуется).
- **Определение типа столбца эвристическое:** число или дата выбираются, если по виду так выглядят не менее 95% непустых значений; коды остаются строками. «1,234» без подсказки читается как 1,234, а не 1234 (и попадает в `report.ambiguous`).
- **Проверки реквизитов арифметические:** `is_inn` говорит, что число могло быть выдано, а не что организация существует. СНИЛС до 001-001-998 контрольным числом не защищены и принимаются по формату. Для счетов подразделений Банка России (БИК оканчивается на 000–002) префикс определён по общему правилу, а ru-kit толкует их иначе (по префиксу счёта 301), поэтому в сверке такие БИК исключены.
- **Формат 1С:** разобраны заголовок, секции расчётных счетов и платёжные документы (ключ=значение). Нестандартные расширения банков сохраняются как столбцы, но не проверяются. Суммы хранятся как `float64`: для копеек до 10¹³ точно, для расчётов сложением лучше `as_decimal=True` у `parse_numbers`.
- Библиотека читает файл в память целиком; для гигабайтных CSV подойдёт `pandas.read_csv(..., encoding=..., sep=";", decimal=",")` с кодировкой, определённой на первых мегабайтах через `detect_encoding`.

## Установка

Пакет выпускается как колесо и архив на странице [Releases](https://github.com/Oleg4311/pandas-ru-io/releases) (контрольные суммы и подтверждение происхождения: `gh attestation verify pandas_ru_io-0.1.0-py3-none-any.whl --repo Oleg4311/pandas-ru-io`):

```bash
pip install https://github.com/Oleg4311/pandas-ru-io/releases/download/v0.1.0/pandas_ru_io-0.1.0-py3-none-any.whl
```

В PyPI пакет пока не публикуется (нужна учётная запись и доверенная публикация); колесо ставится напрямую по ссылке.

## Разработка

```bash
python -m venv .venv && . .venv/bin/activate   # на Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                       # 148 тестов (сверка с ru-kit требует node и npm)
ruff check . && ruff format --check . && mypy
python scripts/eval_encoding.py        # пересчитать docs/encoding-eval.md
```

Лицензия: MIT. Сделано с помощью Claude.

---

## English

**pandas-ru-io** reads and writes Russian tabular data the way Russian Excel produces it: it detects the encoding (cp1251/cp866/KOI8-R/UTF-8/16/32 — bigram language model with a calibrated confidence, a cp1251 fallback below 0.95), the delimiter, Russian numbers (`1 234,56`, `(500,00)`, `12,5 руб.`) and dates (`05.01.2024`, `5 января 2024 г.`, Excel serials), and keeps codes (INN, account numbers, leading zeros) as strings. It also reads/writes **1C bank-statement** files (`1CClientBankExchange`) and validates INN/SNILS/OGRN/OGRNIP/KPP/BIK/account keys. Every parse returns a `ParseReport`; nothing is silently coerced.

Verified: the validators agree with the independently written npm package `@oleg4311/ru-kit` on ~13,000 values; encoding detection is measured on held-out texts (100% from 20 characters on 400 samples per length, `charset-normalizer` needs ≥200 characters to match; calibration: no errors above confidence 0.95); property tests found and fixed a real model flaw; 11 mutations caught; 148 tests, `mypy --strict`. Honest limits: the encoding is guessed among four families, only technical prose and generated table text were available for evaluation, type inference is heuristic, checks are arithmetic only. Released as a wheel (not on PyPI yet). MIT licensed. Built with Claude.
