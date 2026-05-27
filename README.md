# Parabible Avar Mini-Corpus

Локальный мини-параллельный корпус аварского и русского языков на основе данных проекта Parabible.  
Проект включает:

- локальную SQLite-базу с выровненными стихами;
- Flask-интерфейс для поиска по аварскому и русскому тексту;
- скрипт для пополнения глагольной базы примерами из корпуса.

## Структура

```text
parabible_avar_mini_corpus/
├── data/
│   ├── parabible_ava_rus.sqlite
│   ├── аварские глаголы - verbal_database.csv
│   └── аварские глаголы - verbal_database_parabible_examples.csv
├── parabible_avar_corpus.py
├── parabible_fill_verb_examples.py
├── requirements.txt
└── .gitignore
```

## Что внутри

- `parabible_avar_corpus.py`:
  - умеет скачивать и собирать базу из API Parabible;
  - умеет искать по локальной SQLite-базе;
  - поднимает локальный веб-интерфейс.
- `parabible_fill_verb_examples.py`:
  - использует локальную базу корпуса;
  - ищет подходящие примеры для глагольной таблицы;
  - записывает результат в отдельный CSV.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Запуск сайта

```bash
python3 parabible_avar_corpus.py serve
```

По умолчанию сайт откроется на:

```text
http://127.0.0.1:5057
```

## Поиск из командной строки

```bash
python3 parabible_avar_corpus.py search вац --lang avar --search-mode exact --limit 10
```

## Экспорт корпуса в TSV

```bash
python3 parabible_avar_corpus.py export-tsv
```

## Пополнение глагольной таблицы примерами из корпуса

По умолчанию скрипт берёт:

- базу `data/parabible_ava_rus.sqlite`
- входной CSV `data/аварские глаголы - verbal_database.csv`
- выходной CSV `data/аварские глаголы - verbal_database_parabible_examples.csv`

Запуск:

```bash
python3 parabible_fill_verb_examples.py
```

При необходимости пути можно переопределить:

```bash
python3 parabible_fill_verb_examples.py \
  --db data/parabible_ava_rus.sqlite \
  --src-csv "data/аварские глаголы - verbal_database.csv" \
  --out-csv "data/аварские глаголы - verbal_database_parabible_examples.csv"
```

## Источник данных

Корпус основан на данных проекта Parabible и использует аварский и русский тексты как локальную выровненную подвыборку.
