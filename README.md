# Parabible Avar Mini-Corpus

Локальный мини-параллельный корпус аварского и русского языков на основе данных проекта Parabible.  
Проект включает:

- локальную SQLite-базу с выровненными стихами;
- Flask-интерфейс для поиска по аварскому и русскому тексту.

## Структура

```text
parabible_avar_mini_corpus/
├── data/
│   ├── parabible_ava_rus.sqlite
├── parabible_avar_corpus.py
├── requirements.txt
└── .gitignore
```

## Что внутри

- `parabible_avar_corpus.py`:
  - умеет скачивать и собирать базу из API Parabible;
  - умеет искать по локальной SQLite-базе;
  - поднимает локальный веб-интерфейс.

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

## Источник данных

Корпус основан на данных проекта [Parabible](https://github.com/LingConLab/parabible/) и использует аварский и русский тексты как локальную выровненную подвыборку.
