#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from flask import Flask, jsonify, render_template_string, request


API_BASE = "https://lingconlab.ru/parabible/api"
DEFAULT_AVAR_ID = 468
DEFAULT_RUS_ID = 1055
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = str(BASE_DIR / "data" / "parabible_ava_rus.sqlite")
THREAD_LOCAL = threading.local()
STICK_TRANSLATION = str.maketrans({
    "І": "1",
    "Ӏ": "1",
    "ӏ": "1",
    "I": "1",
})


HTML_TEMPLATE = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Parabible Avar Mini-Corpus</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #f6f4ef; color: #1f2328; }
    .page { max-width: 1100px; margin: 0 auto; padding: 24px; }
    .hero { margin-bottom: 18px; }
    .hero h1 { margin: 0 0 8px; font-size: 28px; }
    .hero p { margin: 0; color: #4b5563; }
    .panel { background: white; border-radius: 14px; padding: 18px; box-shadow: 0 8px 28px rgba(0,0,0,0.06); margin-bottom: 18px; }
    .grid { display: grid; grid-template-columns: 2.1fr 1fr 1fr 1fr 1.2fr 1.2fr; gap: 12px; align-items: end; }
    label { display: block; font-size: 13px; margin-bottom: 6px; color: #374151; }
    input, select { width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #cfd6dd; border-radius: 10px; font-size: 14px; }
    button { padding: 10px 14px; border: 0; border-radius: 10px; background: #14532d; color: white; font-size: 14px; cursor: pointer; }
    button:hover { background: #166534; }
    .meta { display: flex; gap: 18px; flex-wrap: wrap; font-size: 14px; color: #4b5563; }
    .match { border-top: 1px solid #e5e7eb; padding-top: 16px; margin-top: 16px; }
    .ref { font-weight: 700; margin-bottom: 8px; }
    .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .col-title { font-size: 12px; color: #6b7280; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .04em; }
    .line { padding: 8px 10px; border-radius: 8px; background: #f8fafc; margin: 6px 0; white-space: pre-wrap; }
    .ctx { margin-top: 10px; padding-left: 14px; border-left: 3px solid #d1d5db; }
    .ctx-current { border-left-color: #14532d; }
    .neighbor-box { margin-top: 12px; }
    .neighbor-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
    .neighbor-toggle { background: #e8efe5; color: #14532d; border: 1px solid #b8c9b5; }
    .neighbor-toggle:hover { background: #dce8d7; }
    .neighbor-panel[hidden] { display: none; }
    .neighbor-panel { margin-top: 10px; }
    .kwic-wrap { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .kwic-hit { font-weight: 600; }
    details.kwic-details { margin-top: 8px; }
    details.kwic-details summary { cursor: pointer; color: #4b5563; font-size: 12px; }
    .kwic-side { margin-top: 8px; }
    .small { font-size: 12px; color: #6b7280; }
    .error { color: #991b1b; white-space: pre-wrap; }
    code { background: #eef2f7; padding: 2px 4px; border-radius: 4px; }
    mark { background: #fde68a; padding: 0 1px; border-radius: 3px; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
    @media (max-width: 900px) { .pair { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>Parabible Avar Mini-Corpus</h1>
      <p>Добро пожаловать на сайт мини-параллельного корпуса аварского языка. Пока доступен только поиск на двух языках с регулярными выражениями, но корпус планирует обновлять функции.</p>
    </div>

    <div class="panel">
      <div class="meta">
        <div><strong>Avar:</strong> {{ avar_title }}</div>
        <div><strong>Russian:</strong> {{ rus_title }}</div>
        <div><strong>Verses:</strong> {{ verse_count }}</div>
      </div>
    </div>

    <div class="panel">
      <form id="search-form">
        <div class="grid">
          <div>
            <label for="pattern">Запрос</label>
            <input id="pattern" name="pattern" placeholder="например: вац или вац***" required>
          </div>
          <div>
            <label for="lang">Искать в</label>
            <select id="lang" name="lang">
              <option value="avar">аварском</option>
              <option value="russian">русском</option>
              <option value="both">обоих</option>
            </select>
          </div>
          <div>
            <label for="window">Контекст</label>
            <input id="window" name="window" type="number" min="0" max="5" value="1">
          </div>
          <div>
            <label for="limit">Лимит</label>
            <input id="limit" name="limit" type="number" min="1" max="500" value="50">
          </div>
          <div>
            <label for="search_mode">Тип поиска</label>
            <select id="search_mode" name="search_mode">
              <option value="exact">точное</option>
              <option value="pattern">шаблон / регулярка</option>
            </select>
          </div>
          <div>
            <label for="view_mode">Выдача</label>
            <select id="view_mode" name="view_mode">
              <option value="verse">стих</option>
              <option value="kwic">KWIC</option>
            </select>
          </div>
        </div>
        <div style="display:flex; gap:12px; margin-top:12px; align-items:center;">
          <label style="display:flex; gap:8px; align-items:center; margin:0;">
            <input id="ignore_case" name="ignore_case" type="checkbox" checked style="width:auto;">
            ignore case
          </label>
          <label style="display:flex; gap:8px; align-items:center; margin:0;">
            <input id="normalize_sticks" name="normalize_sticks" type="checkbox" checked style="width:auto;">
            палочка = 1
          </label>
          <button type="submit">Искать</button>
        </div>
      </form>
      <div id="status" class="small" style="margin-top:10px;"></div>
      <div id="error" class="error" style="margin-top:10px;"></div>
    </div>

    <div id="results"></div>
  </div>

  <script>
    const form = document.getElementById('search-form');
    const results = document.getElementById('results');
    const errorBox = document.getElementById('error');
    const statusBox = document.getElementById('status');

    function toggleNeighbor(id) {
      const el = document.getElementById(id);
      if (!el) return;
      el.hidden = !el.hidden;
    }

    function renderMatch(match) {
      function renderAvar(item) {
        if (item.view_mode === 'kwic') {
          return `
            <div class="line">
              <div class="kwic-wrap">
                <span class="small">…</span>
                <span class="kwic-hit">${item.avar_kwic_html}</span>
                <span class="small">…</span>
              </div>
              <details class="kwic-details">
                <summary>показать левый / правый контекст</summary>
                <div class="kwic-side"><strong>Left:</strong> ${item.avar_left_html}</div>
                <div class="kwic-side"><strong>Right:</strong> ${item.avar_right_html}</div>
              </details>
            </div>
          `;
        }
        return `<div class="line">${item.avar_html}</div>`;
      }
      function renderNeighbor(item, panelId) {
        if (!item) return '';
        return `
          <div id="${panelId}" class="neighbor-panel" hidden>
            <div class="small">${item.human_ref}</div>
            <div class="pair">
              <div>
                <div class="col-title">Avar</div>
                ${renderAvar(item)}
              </div>
              <div>
                <div class="col-title">Russian</div>
                <div class="line">${item.russian_html}</div>
              </div>
            </div>
          </div>
        `;
      }

      const hitIndex = match.context.findIndex(item => item.is_hit);
      const prevItem = hitIndex > 0 ? match.context[hitIndex - 1] : null;
      const nextItem = hitIndex >= 0 && hitIndex < match.context.length - 1 ? match.context[hitIndex + 1] : null;
      const baseId = match.ref.replaceAll(':', '-');
      const prevId = `prev-${baseId}`;
      const nextId = `next-${baseId}`;
      const neighborButtons = `
        <div class="neighbor-actions">
          ${prevItem ? `<button type="button" class="neighbor-toggle" onclick="toggleNeighbor('${prevId}')">показать предыдущий стих</button>` : ''}
          ${nextItem ? `<button type="button" class="neighbor-toggle" onclick="toggleNeighbor('${nextId}')">показать следующий стих</button>` : ''}
        </div>
      `;

      return `
        <div class="panel match">
          <div class="ref">${match.human_ref} <span class="small">(${match.ref})</span></div>
          <div class="pair">
            <div>
              <div class="col-title">Avar</div>
              ${renderAvar(match)}
            </div>
            <div>
              <div class="col-title">Russian</div>
              <div class="line">${match.russian_html}</div>
            </div>
          </div>
          <div class="neighbor-box">
            ${neighborButtons}
            ${renderNeighbor(prevItem, prevId)}
            ${renderNeighbor(nextItem, nextId)}
          </div>
        </div>
      `;
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errorBox.textContent = '';
      results.innerHTML = '';
      statusBox.textContent = 'Ищу...';
      const params = new URLSearchParams({
        pattern: document.getElementById('pattern').value,
        lang: document.getElementById('lang').value,
        window: document.getElementById('window').value,
        limit: document.getElementById('limit').value,
        search_mode: document.getElementById('search_mode').value,
        view_mode: document.getElementById('view_mode').value,
        ignore_case: document.getElementById('ignore_case').checked ? '1' : '0',
        normalize_sticks: document.getElementById('normalize_sticks').checked ? '1' : '0',
      });
      try {
        const resp = await fetch('/api/search?' + params.toString());
        const data = await resp.json();
        if (!resp.ok) {
          errorBox.textContent = data.error || 'search failed';
          statusBox.textContent = '';
          return;
        }
        statusBox.textContent = `Найдено: ${data.count}`;
        results.innerHTML = data.results.map(renderMatch).join('');
      } catch (err) {
        errorBox.textContent = String(err);
        statusBox.textContent = '';
      }
    });
  </script>
</body>
</html>
"""


@dataclass(frozen=True)
class VerseRef:
    book_id: int
    chapter_id: int
    verse_id: int

    @property
    def ref(self) -> str:
        return f"{self.book_id:02d}:{self.chapter_id:03d}:{self.verse_id:03d}"


class ParabibleAPI:
    def __init__(self, base_url: str, pause: float = 0.0, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.pause = pause
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str, **params) -> dict:
        url = f"{self.base_url}{path}"
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        if self.pause:
            time.sleep(self.pause)
        return response.json()

    def get_translation_meta(self, translation_id: int) -> dict:
        return self._get("/get/translation_meta", id=translation_id)

    def get_book_abbrs(self) -> dict:
        return self._get("/get/book_title_abbrs")

    def get_book_ids(self, translation_ids: list[int], mode: str = "all") -> list[int]:
        return self._get("/get/book_ids", mode=mode, translation_id=translation_ids)["books"]

    def get_chapter_ids(self, translation_ids: list[int], book_id: int, mode: str = "all") -> list[int]:
        return self._get(
            "/get/chapter_ids",
            mode=mode,
            translation_id=translation_ids,
            book_id=book_id,
        )["chapters"]

    def get_verse_ids(
        self,
        translation_ids: list[int],
        book_id: int,
        chapter_id: int,
        mode: str = "all",
    ) -> list[int]:
        return self._get(
            "/get/verse_ids",
            mode=mode,
            translation_id=translation_ids,
            book_id=book_id,
            chapter_id=chapter_id,
        )["verses"]

    def get_verse(self, translation_id: int, ref: VerseRef) -> str | None:
        return self._get(
            "/get/verse",
            translation_id=translation_id,
            book_id=ref.book_id,
            chapter=ref.chapter_id,
            verse=ref.verse_id,
        )["verse"]


def get_thread_api(base_url: str, pause: float, timeout: int) -> ParabibleAPI:
    api = getattr(THREAD_LOCAL, "api", None)
    if api is None or api.base_url != base_url or api.pause != pause or api.timeout != timeout:
        api = ParabibleAPI(base_url, pause=pause, timeout=timeout)
        THREAD_LOCAL.api = api
    return api


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS aligned_verses (
            ref TEXT PRIMARY KEY,
            book_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            verse_id INTEGER NOT NULL,
            avar TEXT,
            russian TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_aligned_verses_book_chapter_verse
        ON aligned_verses (book_id, chapter_id, verse_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_aligned_verses_ref
        ON aligned_verses (ref)
        """
    )
    return conn


def iter_common_refs(api: ParabibleAPI, avar_id: int, rus_id: int) -> Iterable[VerseRef]:
    translation_ids = [avar_id, rus_id]
    for book_id in api.get_book_ids(translation_ids, mode="all"):
        for chapter_id in api.get_chapter_ids(translation_ids, book_id, mode="all"):
            for verse_id in api.get_verse_ids(translation_ids, book_id, chapter_id, mode="all"):
                yield VerseRef(book_id, chapter_id, verse_id)


def fetch_aligned_row(ref: VerseRef, avar_id: int, rus_id: int, base_url: str, pause: float, timeout: int):
    api = get_thread_api(base_url, pause, timeout)
    avar = api.get_verse(avar_id, ref)
    russian = api.get_verse(rus_id, ref)
    return (ref.ref, ref.book_id, ref.chapter_id, ref.verse_id, avar, russian)


def metadata_get(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def human_ref(ref: sqlite3.Row | tuple, book_abbrs: dict[str, str]) -> str:
    if isinstance(ref, sqlite3.Row):
        book_id = ref["book_id"]
        chapter_id = ref["chapter_id"]
        verse_id = ref["verse_id"]
    else:
        book_id, chapter_id, verse_id = ref
    abbr = book_abbrs.get(str(book_id), str(book_id))
    return f"{abbr} {chapter_id}:{verse_id}"


def normalize_sticks(text: str) -> str:
    return text.translate(STICK_TRANSLATION)


def wildcard_to_regex(pattern: str) -> str:
    out: list[str] = []
    for ch in pattern:
        if ch == "*":
            out.append(".")
        else:
            out.append(ch)
    return "".join(out)


def compile_pattern(
    pattern: str,
    ignore_case: bool,
    search_mode: str = "exact",
    normalize: bool = False,
) -> re.Pattern[str]:
    if normalize:
        pattern = normalize_sticks(pattern)
    if search_mode == "exact":
        pattern = rf"(?<!\w){re.escape(pattern)}(?!\w)"
    else:
        pattern = wildcard_to_regex(pattern)
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(pattern, flags)


def build_search_target(text: str, normalize: bool) -> str:
    if normalize:
        return normalize_sticks(text)
    return text


def find_match_spans(text: str, pattern: re.Pattern[str], normalize: bool) -> list[tuple[int, int]]:
    target = build_search_target(text, normalize)
    spans: list[tuple[int, int]] = []
    for match in pattern.finditer(target):
        start, end = match.span()
        if start == end:
            continue
        spans.append((start, end))
    return spans


def merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    merged = [spans[0]]
    for start, end in spans[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def highlight_html(text: str, spans: list[tuple[int, int]]) -> str:
    merged = merge_spans(spans)
    if not merged:
        return html.escape(text)
    out: list[str] = []
    pos = 0
    for start, end in merged:
        if pos < start:
            out.append(html.escape(text[pos:start]))
        out.append("<mark>")
        out.append(html.escape(text[start:end]))
        out.append("</mark>")
        pos = end
    if pos < len(text):
        out.append(html.escape(text[pos:]))
    return "".join(out)


def split_kwic_html(text: str, spans: list[tuple[int, int]]) -> tuple[str, str, str]:
    merged = merge_spans(spans)
    if not merged:
        escaped = html.escape(text)
        return escaped, escaped, escaped
    start, end = merged[0]
    left = html.escape(text[:start])
    hit = highlight_html(text[start:end], [(0, end - start)])
    right = html.escape(text[end:])
    return left, hit, right


def fetch_context_rows(
    conn: sqlite3.Connection,
    book_id: int,
    chapter_id: int,
    verse_id: int,
    window: int,
) -> list[sqlite3.Row]:
    start_verse = max(1, verse_id - window)
    end_verse = verse_id + window
    cur = conn.execute(
        """
        SELECT ref, book_id, chapter_id, verse_id, avar, russian
        FROM aligned_verses
        WHERE book_id = ? AND chapter_id = ? AND verse_id BETWEEN ? AND ?
        ORDER BY verse_id
        """,
        (book_id, chapter_id, start_verse, end_verse),
    )
    return cur.fetchall()


def row_matches(row: sqlite3.Row, pattern: re.Pattern[str], lang: str, normalize: bool) -> bool:
    avar = row["avar"] or ""
    russian = row["russian"] or ""
    if lang == "avar":
        return bool(pattern.search(build_search_target(avar, normalize)))
    if lang == "russian":
        return bool(pattern.search(build_search_target(russian, normalize)))
    return bool(
        pattern.search(build_search_target(avar, normalize))
        or pattern.search(build_search_target(russian, normalize))
    )


def search_rows(
    conn: sqlite3.Connection,
    pattern_text: str,
    lang: str,
    search_mode: str,
    normalize: bool,
    view_mode: str,
    ignore_case: bool,
    limit: int,
    window: int,
) -> tuple[list[dict], int]:
    pattern = compile_pattern(pattern_text, ignore_case, search_mode, normalize)
    book_abbrs = json.loads(metadata_get(conn, "book_abbrs", "{}"))
    cur = conn.execute(
        """
        SELECT ref, book_id, chapter_id, verse_id, avar, russian
        FROM aligned_verses
        ORDER BY book_id, chapter_id, verse_id
        """
    )

    results = []
    total = 0
    for row in cur:
        if not row_matches(row, pattern, lang, normalize):
            continue
        total += 1
        if len(results) >= limit:
            continue
        ctx_rows = fetch_context_rows(conn, row["book_id"], row["chapter_id"], row["verse_id"], window)
        avar_text = row["avar"] or ""
        russian_text = row["russian"] or ""
        avar_spans = find_match_spans(avar_text, pattern, normalize) if lang in {"avar", "both"} else []
        russian_spans = find_match_spans(russian_text, pattern, normalize) if lang in {"russian", "both"} else []
        avar_left_html, avar_kwic_html, avar_right_html = split_kwic_html(avar_text, avar_spans)
        results.append(
            {
                "ref": row["ref"],
                "human_ref": human_ref(row, book_abbrs),
                "avar": avar_text,
                "russian": russian_text,
                "view_mode": view_mode,
                "avar_html": highlight_html(avar_text, avar_spans),
                "russian_html": highlight_html(russian_text, russian_spans),
                "avar_left_html": avar_left_html,
                "avar_kwic_html": avar_kwic_html,
                "avar_right_html": avar_right_html,
                "context": [
                    {
                        "ref": ctx["ref"],
                        "human_ref": human_ref(ctx, book_abbrs),
                        "avar": ctx["avar"] or "",
                        "russian": ctx["russian"] or "",
                        "view_mode": view_mode,
                        "avar_html": highlight_html(
                            ctx["avar"] or "",
                            find_match_spans(ctx["avar"] or "", pattern, normalize)
                            if lang in {"avar", "both"}
                            else [],
                        ),
                        "russian_html": highlight_html(
                            ctx["russian"] or "",
                            find_match_spans(ctx["russian"] or "", pattern, normalize)
                            if lang in {"russian", "both"}
                            else [],
                        ),
                        "avar_left_html": split_kwic_html(
                            ctx["avar"] or "",
                            find_match_spans(ctx["avar"] or "", pattern, normalize)
                            if lang in {"avar", "both"}
                            else [],
                        )[0],
                        "avar_kwic_html": split_kwic_html(
                            ctx["avar"] or "",
                            find_match_spans(ctx["avar"] or "", pattern, normalize)
                            if lang in {"avar", "both"}
                            else [],
                        )[1],
                        "avar_right_html": split_kwic_html(
                            ctx["avar"] or "",
                            find_match_spans(ctx["avar"] or "", pattern, normalize)
                            if lang in {"avar", "both"}
                            else [],
                        )[2],
                        "is_hit": ctx["verse_id"] == row["verse_id"],
                    }
                    for ctx in ctx_rows
                ],
            }
        )
    return results, total


def build_corpus(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser().resolve()
    api = ParabibleAPI(args.api_base, pause=args.pause, timeout=args.timeout)
    conn = init_db(db_path)

    avar_meta = api.get_translation_meta(args.avar_id)
    rus_meta = api.get_translation_meta(args.rus_id)
    book_abbrs = api.get_book_abbrs()
    conn.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
        [
            ("api_base", args.api_base),
            ("avar_translation_id", str(args.avar_id)),
            ("rus_translation_id", str(args.rus_id)),
            ("avar_translation_meta", json.dumps(avar_meta, ensure_ascii=False)),
            ("rus_translation_meta", json.dumps(rus_meta, ensure_ascii=False)),
            ("book_abbrs", json.dumps(book_abbrs, ensure_ascii=False)),
        ],
    )
    conn.commit()

    refs = list(iter_common_refs(api, args.avar_id, args.rus_id))
    print(f"common aligned refs: {len(refs)}", file=sys.stderr)

    rows = []
    total = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                fetch_aligned_row,
                ref,
                args.avar_id,
                args.rus_id,
                args.api_base,
                args.pause,
                args.timeout,
            )
            for ref in refs
        ]
        for future in as_completed(futures):
            rows.append(future.result())
            total += 1
            if len(rows) >= args.batch_size:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO aligned_verses
                    (ref, book_id, chapter_id, verse_id, avar, russian)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()
                print(f"saved {total}/{len(refs)} verses", file=sys.stderr)
                rows.clear()

    if rows:
        conn.executemany(
            """
            INSERT OR REPLACE INTO aligned_verses
            (ref, book_id, chapter_id, verse_id, avar, russian)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM aligned_verses").fetchone()[0]
    print(f"done: {count} aligned verses in {db_path}")
    return 0


def search_corpus(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser().resolve()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    results, total = search_rows(
        conn=conn,
        pattern_text=args.pattern,
        lang=args.lang,
        search_mode=args.search_mode,
        normalize=args.normalize_sticks,
        view_mode=args.view_mode,
        ignore_case=args.ignore_case,
        limit=args.limit,
        window=args.window,
    )

    print(f"total matches: {total}")
    for match in results:
        print(f"\n=== {match['human_ref']} ({match['ref']}) ===")
        print(f"AVA: {match['avar']}")
        print(f"RUS: {match['russian']}")
        for ctx in match["context"]:
            marker = ">>" if ctx["is_hit"] else "  "
            print(f"{marker} {ctx['human_ref']}")
            print(f"{marker} AVA: {ctx['avar']}")
            print(f"{marker} RUS: {ctx['russian']}")
    if total == 0:
        print("no matches")
    return 0


def export_tsv(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        """
        SELECT ref, avar, russian
        FROM aligned_verses
        ORDER BY book_id, chapter_id, verse_id
        """
    )
    with out_path.open("w", encoding="utf-8") as f:
        f.write("ref\tavar\trussian\n")
        for ref, avar, russian in cur:
            f.write(
                f"{ref}\t{(avar or '').replace(chr(9), ' ')}\t{(russian or '').replace(chr(9), ' ')}\n"
            )
    print(out_path)
    return 0


def serve_web(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 1

    app = Flask(__name__)

    def get_conn() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @app.get("/")
    def index():
        conn = get_conn()
        avar_meta = json.loads(metadata_get(conn, "avar_translation_meta", "{}") or "{}")
        rus_meta = json.loads(metadata_get(conn, "rus_translation_meta", "{}") or "{}")
        verse_count = conn.execute("SELECT COUNT(*) FROM aligned_verses").fetchone()[0]
        avar_title = avar_meta.get("vernacular_title") or avar_meta.get("english_title") or f"id {DEFAULT_AVAR_ID}"
        rus_title = rus_meta.get("vernacular_title") or rus_meta.get("english_title") or f"id {DEFAULT_RUS_ID}"
        return render_template_string(
            HTML_TEMPLATE,
            db_path=str(db_path),
            avar_title=avar_title,
            rus_title=rus_title,
            verse_count=verse_count,
        )

    @app.get("/api/search")
    def api_search():
        pattern = request.args.get("pattern", "")
        lang = request.args.get("lang", "avar")
        search_mode = request.args.get("search_mode", "exact")
        view_mode = request.args.get("view_mode", "verse")
        window = request.args.get("window", default=1, type=int)
        limit = request.args.get("limit", default=50, type=int)
        ignore_case = request.args.get("ignore_case", "1") == "1"
        normalize_sticks_flag = request.args.get("normalize_sticks", "1") == "1"

        if not pattern:
            return jsonify({"error": "pattern is required"}), 400
        if lang not in {"avar", "russian", "both"}:
            return jsonify({"error": "lang must be avar, russian or both"}), 400
        if search_mode not in {"exact", "pattern"}:
            return jsonify({"error": "search_mode must be exact or pattern"}), 400
        if view_mode not in {"verse", "kwic"}:
            return jsonify({"error": "view_mode must be verse or kwic"}), 400
        if window < 0 or window > 5:
            return jsonify({"error": "window must be between 0 and 5"}), 400
        if limit < 1 or limit > 500:
            return jsonify({"error": "limit must be between 1 and 500"}), 400

        try:
            conn = get_conn()
            results, total = search_rows(
                conn=conn,
                pattern_text=pattern,
                lang=lang,
                search_mode=search_mode,
                normalize=normalize_sticks_flag,
                view_mode=view_mode,
                ignore_case=ignore_case,
                limit=limit,
                window=window,
            )
        except re.error as exc:
            return jsonify({"error": f"invalid regex: {exc}"}), 400

        return jsonify({"count": total, "results": results})

    print(f"open locally: http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mini-corpus builder/searcher for Avar-Russian Parabible data."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Download aligned Avar-Russian verses into SQLite.")
    build.add_argument("--db", default=DEFAULT_DB)
    build.add_argument("--api-base", default=API_BASE)
    build.add_argument("--avar-id", type=int, default=DEFAULT_AVAR_ID)
    build.add_argument("--rus-id", type=int, default=DEFAULT_RUS_ID)
    build.add_argument("--batch-size", type=int, default=300)
    build.add_argument("--pause", type=float, default=0.0)
    build.add_argument("--timeout", type=int, default=30)
    build.add_argument("--workers", type=int, default=16)
    build.set_defaults(func=build_corpus)

    search = subparsers.add_parser("search", help="Regex search over aligned verses.")
    search.add_argument("pattern", help="Python regex.")
    search.add_argument("--db", default=DEFAULT_DB)
    search.add_argument("--lang", choices=["avar", "russian", "both"], default="avar")
    search.add_argument("--search-mode", choices=["exact", "pattern"], default="exact")
    search.add_argument("--normalize-sticks", action="store_true")
    search.add_argument("--view-mode", choices=["verse", "kwic"], default="verse")
    search.add_argument("--window", type=int, default=1, help="How many neighboring verses to show.")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--ignore-case", action="store_true")
    search.set_defaults(func=search_corpus)

    export = subparsers.add_parser("export-tsv", help="Export aligned verses to TSV.")
    export.add_argument("--db", default=DEFAULT_DB)
    export.add_argument("--out", default=str(BASE_DIR / "data" / "parabible_ava_rus.tsv"))
    export.set_defaults(func=export_tsv)

    serve = subparsers.add_parser("serve", help="Run a local web UI for regex search.")
    serve.add_argument("--db", default=DEFAULT_DB)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=5057)
    serve.set_defaults(func=serve_web)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
