#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "parabible_ava_rus.sqlite"
DEFAULT_SRC_CSV = BASE_DIR / "data" / "аварские глаголы - verbal_database.csv"
DEFAULT_OUT_CSV = BASE_DIR / "data" / "аварские глаголы - verbal_database_parabible_examples.csv"

TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
STICK_TRANSLATION = str.maketrans({
    "І": "1",
    "Ӏ": "1",
    "ӏ": "1",
    "I": "1",
})
LATIN_TO_CYR = str.maketrans({
    "a": "а",
    "e": "е",
    "o": "о",
    "u": "у",
    "i": "и",
    "A": "А",
    "E": "Е",
    "O": "О",
    "U": "У",
    "I": "И",
})
RU_TOKEN_RE = re.compile(r"[А-Яа-яЁё-]+")


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def normalize_text(text: str) -> str:
    text = strip_accents(text)
    text = text.translate(STICK_TRANSLATION)
    return text


def normalize_form_piece(text: str) -> str:
    text = normalize_text(text)
    text = text.translate(LATIN_TO_CYR)
    text = text.replace("/", "").replace("-", "").replace(" ", "")
    return text


def build_form(stem: str, suffix: str) -> str:
    stem_n = normalize_form_piece(stem)
    suffix_n = normalize_form_piece(suffix).lstrip("-")
    return stem_n + suffix_n


def normalized_suffix(text: str) -> str:
    return normalize_form_piece(text).lstrip("-")


def load_verses(db_path: Path):
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        """
        SELECT ref, book_id, chapter_id, verse_id, avar, russian
        FROM aligned_verses
        ORDER BY book_id, chapter_id, verse_id
        """
    )
    verses = []
    token_index: dict[str, list[int]] = defaultdict(list)
    bigram_index: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, (ref, book_id, chapter_id, verse_id, avar, russian) in enumerate(cur.fetchall()):
        avar = avar or ""
        russian = russian or ""
        norm_avar = normalize_text(avar)
        tokens = TOKEN_RE.findall(norm_avar.lower())
        verses.append(
            {
                "ref": ref,
                "book_id": book_id,
                "chapter_id": chapter_id,
                "verse_id": verse_id,
                "avar": avar,
                "russian": russian,
                "tokens": tokens,
            }
        )
        for tok in set(tokens):
            token_index[tok].append(i)
        for j in range(len(tokens) - 1):
            bigram_index[(tokens[j], tokens[j + 1])].append(i)
    return verses, token_index, bigram_index


def verse_score(verse: dict) -> tuple[int, int]:
    text = verse["avar"]
    token_count = len(verse["tokens"])
    score = 0
    if 5 <= token_count <= 20:
        score += 5
    elif 3 <= token_count <= 30:
        score += 3
    if any(p in text for p in [",", ";", ":"]):
        score += 1
    if verse["russian"]:
        score += 1
    return (score, token_count)


def find_best_example(form: str, verses: list[dict], token_index: dict[str, list[int]]):
    norm_form = normalize_text(form).lower()
    hits = token_index.get(norm_form, [])
    if not hits:
        return None, 0
    candidates = [verses[i] for i in hits]
    candidates.sort(key=verse_score, reverse=True)
    return candidates[0], len(hits)


def build_agreement_variants(form: str, agreement_slot: str) -> list[str]:
    variants = [form]
    if agreement_slot == "0" or "б" not in form:
        return variants
    for repl in ["й", "в", "р"]:
        variants.append(form.replace("б", repl))
    # dedupe preserve order
    out = []
    seen = set()
    for v in variants:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def find_best_example_variants(forms: list[str], verses: list[dict], token_index: dict[str, list[int]]):
    best = None
    best_form = ""
    total_hits_set = set()
    for form in forms:
        example, count = find_best_example(form, verses, token_index)
        if count:
            norm_form = normalize_text(form).lower()
            # collect exact hit verse ids
            # this keeps count stable across variants
            hits = token_index.get(norm_form, [])
            total_hits_set.update(hits)
        if example and (best is None or verse_score(example) > verse_score(best)):
            best = example
            best_form = form
    return best, best_form, len(total_hits_set)


def perfect_stem_variants(row: dict) -> list[tuple[str, str]]:
    stem0 = row.get("stem0", "") or row.get("stеm", "")
    verb_class = row.get("verb class", "")
    stem0_norm = normalize_form_piece(stem0)
    if not stem0_norm:
        return []
    if verb_class in {"6", "7", "8"}:
        return [("n", stem0_norm + "н")]
    if verb_class in {"3n", "3/4"}:
        return [("un", stem0_norm + "ун"), ("on", stem0_norm + "он")]
    return [("un", stem0_norm + "ун")]


def find_best_bigram_example_variants(
    form_variants: list[str],
    aux_variants: list[str],
    verses: list[dict],
    bigram_index: dict[tuple[str, str], list[int]],
):
    total_hits_set = set()
    best = None
    best_form = ""
    best_aux = ""
    for form in form_variants:
        norm_form = normalize_text(form).lower()
        for aux in aux_variants:
            key = (norm_form, aux)
            hits = bigram_index.get(key, [])
            if not hits:
                continue
            total_hits_set.update(hits)
            candidates = [verses[i] for i in hits]
            candidates.sort(key=verse_score, reverse=True)
            if candidates and (best is None or verse_score(candidates[0]) > verse_score(best)):
                best = candidates[0]
                best_form = form
                best_aux = aux
    return best, best_form, best_aux, len(total_hits_set)


def compound_participle_variants(aorist_form: str) -> list[tuple[str, str]]:
    if not aorist_form:
        return []
    base = normalize_form_piece(aorist_form)
    if not base:
        return []
    if base.endswith("на"):
        base = base[:-2]
    return [(marker, f"{base}ра{marker}") for marker in ["й", "в", "б", "р"]]


def find_best_compound_example(
    participle_variants: list[tuple[str, str]],
    aux_map: dict[str, str],
    verses: list[dict],
    bigram_index: dict[tuple[str, str], list[int]],
):
    total_hits_set = set()
    best = None
    best_form = ""
    best_aux = ""
    best_marker = ""
    for marker, form in participle_variants:
        aux = aux_map.get(marker)
        if not aux:
            continue
        ex, found_form, found_aux, count = find_best_bigram_example_variants(
            [form], [aux], verses, bigram_index
        )
        if count:
            norm_form = normalize_text(form).lower()
            hits = bigram_index.get((norm_form, aux), [])
            total_hits_set.update(hits)
        if ex and (best is None or verse_score(ex) > verse_score(best)):
            best = ex
            best_form = found_form
            best_aux = found_aux
            best_marker = marker
    return best, best_form, best_aux, best_marker, len(total_hits_set)


def same_imperative_masdar_suffix(row: dict) -> bool:
    imp = row.get("impеrаtivе", "")
    masdar = row.get("mаsdаr", "")
    if not imp or not masdar or imp == "N":
        return False
    return normalized_suffix(imp) == normalized_suffix(masdar)


def guess_russian_form_hint(text: str) -> tuple[str, str]:
    text = (text or "").strip()
    if not text:
        return "", ""
    lowered = text.lower()
    patterns = [
        (r"\b(пусть\s+[А-Яа-яЁё-]+)", "jussive_phrase"),
        (r"\b(пускай\s+[А-Яа-яЁё-]+)", "jussive_phrase"),
        (r"\b(да\s+[А-Яа-яЁё-]+)", "jussive_phrase"),
        (r"\b(не\s+[А-Яа-яЁё-]+)", "negative_command"),
    ]
    for pat, label in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(1), label

    tokens = RU_TOKEN_RE.findall(text)
    imperative_like = []
    finite_like = []
    for tok in tokens:
        low = tok.lower()
        if len(low) <= 2:
            continue
        if low.endswith(("йте", "ите", "ай", "яй", "уй", "и", "й", "ь")):
            imperative_like.append(tok)
        elif low.endswith(("ет", "ёт", "ут", "ют", "ит", "ат", "ят", "ем", "им")):
            finite_like.append(tok)
    if imperative_like:
        return imperative_like[0], "imperative_like_token"
    if finite_like:
        return finite_like[0], "finite_like_token"
    return "", ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fill the verbal database with examples from the local Avar-Russian Parabible mini-corpus."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--src-csv", default=str(DEFAULT_SRC_CSV))
    parser.add_argument("--out-csv", default=str(DEFAULT_OUT_CSV))
    return parser


def main():
    args = build_parser().parse_args()
    db_path = Path(args.db).expanduser().resolve()
    src_csv = Path(args.src_csv).expanduser().resolve()
    out_csv = Path(args.out_csv).expanduser().resolve()

    verses, token_index, bigram_index = load_verses(db_path)
    print(f"Loaded {len(verses)} verses")

    with src_csv.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        extra_fields = [
            "parabible_present_form",
            "parabible_future_form",
            "parabible_aorist_form",
            "parabible_imperative_form",
            "parabible_imperative_a_form",
            "parabible_match_form",
            "parabible_match_tense",
            "parabible_match_ref",
            "parabible_match_avar",
            "parabible_match_russian",
            "parabible_match_source",
            "parabible_match_count",
            "parabible_imperative_match_ref",
            "parabible_imperative_match_avar",
            "parabible_imperative_match_russian",
            "parabible_imperative_match_source",
            "parabible_imperative_match_count",
            "parabible_imperative_a_match_ref",
            "parabible_imperative_a_match_avar",
            "parabible_imperative_a_match_russian",
            "parabible_imperative_a_match_source",
            "parabible_imperative_a_match_count",
            "parabible_imperative_total_count",
            "parabible_imperative_masdar_same_suffix",
            "parabible_imperative_ru_hint",
            "parabible_imperative_ru_hint_type",
            "parabible_perfect_form",
            "parabible_perfect_aux",
            "parabible_perfect_match_ref",
            "parabible_perfect_match_avar",
            "parabible_perfect_match_russian",
            "parabible_perfect_match_source",
            "parabible_perfect_match_count",
            "parabible_perfect_found_variant",
            "parabible_pluperfect_form",
            "parabible_pluperfect_aux",
            "parabible_pluperfect_match_ref",
            "parabible_pluperfect_match_avar",
            "parabible_pluperfect_match_russian",
            "parabible_pluperfect_match_source",
            "parabible_pluperfect_match_count",
            "parabible_pluperfect_found_variant",
            "parabible_compound_present_form",
            "parabible_compound_present_aux",
            "parabible_compound_present_marker",
            "parabible_compound_present_match_ref",
            "parabible_compound_present_match_avar",
            "parabible_compound_present_match_russian",
            "parabible_compound_present_match_source",
            "parabible_compound_present_match_count",
            "parabible_compound_past_form",
            "parabible_compound_past_aux",
            "parabible_compound_past_marker",
            "parabible_compound_past_match_ref",
            "parabible_compound_past_match_avar",
            "parabible_compound_past_match_russian",
            "parabible_compound_past_match_source",
            "parabible_compound_past_match_count",
            "parabible_compound_future_form",
            "parabible_compound_future_aux",
            "parabible_compound_future_marker",
            "parabible_compound_future_match_ref",
            "parabible_compound_future_match_avar",
            "parabible_compound_future_match_russian",
            "parabible_compound_future_match_source",
            "parabible_compound_future_match_count",
        ]
        out_fields = fieldnames + [f for f in extra_fields if f not in fieldnames]

        rows = []
        matched = 0
        for row in reader:
            stem = row.get("stеm", "")
            pres = row.get("prеsеncе", "")
            fut = row.get("futurе", "")
            aor = row.get("аorist", "")
            imp = row.get("impеrаtivе", "")
            agreement_slot = row.get("аgrееmеnt_slot", "0")

            present_form = build_form(stem, pres) if stem and pres else ""
            future_form = build_form(stem, fut) if stem and fut else ""
            aorist_form = build_form(stem, aor) if stem and aor else ""
            imperative_form = build_form(row.get("stem0", "") or stem, imp) if (row.get("stem0", "") or stem) and imp and imp != "N" else ""
            imperative_suffix_norm = normalize_form_piece(imp).lstrip("-")
            imperative_a_form = ""
            if imperative_form and imperative_suffix_norm == "е":
                imperative_a_form = normalize_form_piece(row.get("stem0", "") or stem) + "а"

            row["parabible_present_form"] = present_form
            row["parabible_future_form"] = future_form
            row["parabible_aorist_form"] = aorist_form
            row["parabible_imperative_form"] = imperative_form
            row["parabible_imperative_a_form"] = imperative_a_form
            row["parabible_imperative_masdar_same_suffix"] = "yes" if same_imperative_masdar_suffix(row) else ""
            row["parabible_imperative_ru_hint"] = ""
            row["parabible_imperative_ru_hint_type"] = ""

            example = None
            chosen_form = ""
            chosen_tense = ""
            chosen_count = 0
            for tense, form in [
                ("present", present_form),
                ("future", future_form),
                ("aorist", aorist_form),
            ]:
                if not form:
                    continue
                variants = build_agreement_variants(form, agreement_slot)
                example, found_form, count = find_best_example_variants(variants, verses, token_index)
                if example:
                    chosen_form = found_form
                    chosen_tense = tense
                    chosen_count = count
                    break

            if example:
                matched += 1
                row["parabible_match_form"] = chosen_form
                row["parabible_match_tense"] = chosen_tense
                row["parabible_match_ref"] = example["ref"]
                row["parabible_match_avar"] = example["avar"]
                row["parabible_match_russian"] = example["russian"]
                row["parabible_match_source"] = "Parabible mini-corpus: Avar 468 + Russian 1055"
                row["parabible_match_count"] = str(chosen_count)
            else:
                row["parabible_match_form"] = ""
                row["parabible_match_tense"] = ""
                row["parabible_match_ref"] = ""
                row["parabible_match_avar"] = ""
                row["parabible_match_russian"] = ""
                row["parabible_match_source"] = ""
                row["parabible_match_count"] = "0"

            imp_example = None
            imp_count = 0
            if imperative_form:
                imp_variants = build_agreement_variants(imperative_form, agreement_slot)
                imp_example, _, imp_count = find_best_example_variants(imp_variants, verses, token_index)
            if imp_example:
                row["parabible_imperative_match_ref"] = imp_example["ref"]
                row["parabible_imperative_match_avar"] = imp_example["avar"]
                row["parabible_imperative_match_russian"] = imp_example["russian"]
                row["parabible_imperative_match_source"] = "Parabible mini-corpus: Avar 468 + Russian 1055"
                row["parabible_imperative_match_count"] = str(imp_count)
                if row["parabible_imperative_masdar_same_suffix"]:
                    hint, hint_type = guess_russian_form_hint(imp_example["russian"])
                    row["parabible_imperative_ru_hint"] = hint
                    row["parabible_imperative_ru_hint_type"] = hint_type
            else:
                row["parabible_imperative_match_ref"] = ""
                row["parabible_imperative_match_avar"] = ""
                row["parabible_imperative_match_russian"] = ""
                row["parabible_imperative_match_source"] = ""
                row["parabible_imperative_match_count"] = "0"

            imp_a_example = None
            imp_a_count = 0
            if imperative_a_form:
                imp_a_variants = build_agreement_variants(imperative_a_form, agreement_slot)
                imp_a_example, _, imp_a_count = find_best_example_variants(imp_a_variants, verses, token_index)
            if imp_a_example:
                row["parabible_imperative_a_match_ref"] = imp_a_example["ref"]
                row["parabible_imperative_a_match_avar"] = imp_a_example["avar"]
                row["parabible_imperative_a_match_russian"] = imp_a_example["russian"]
                row["parabible_imperative_a_match_source"] = "Parabible mini-corpus: Avar 468 + Russian 1055"
                row["parabible_imperative_a_match_count"] = str(imp_a_count)
            else:
                row["parabible_imperative_a_match_ref"] = ""
                row["parabible_imperative_a_match_avar"] = ""
                row["parabible_imperative_a_match_russian"] = ""
                row["parabible_imperative_a_match_source"] = ""
                row["parabible_imperative_a_match_count"] = "0"

            row["parabible_imperative_total_count"] = str(imp_count + imp_a_count)

            perfect_base_variants = perfect_stem_variants(row)
            perfect_auxes = ["уго", "буго", "йуго", "вуго", "руго"]
            pluperfect_auxes = ["ук1ана", "бук1ана", "йук1ана", "вук1ана", "рук1ана"]

            perfect_forms = []
            for suffix_name, base_form in perfect_base_variants:
                perfect_forms.extend((suffix_name, v) for v in build_agreement_variants(base_form, agreement_slot))
            best_perfect = None
            best_perfect_form = ""
            best_perfect_aux = ""
            best_perfect_variant = ""
            best_perfect_count = 0
            if not example and perfect_forms:
                for suffix_name, form_variant in perfect_forms:
                    ex, found_form, found_aux, count = find_best_bigram_example_variants(
                        [form_variant], perfect_auxes, verses, bigram_index
                    )
                    if ex and (best_perfect is None or verse_score(ex) > verse_score(best_perfect)):
                        best_perfect = ex
                        best_perfect_form = found_form
                        best_perfect_aux = found_aux
                        best_perfect_variant = suffix_name
                        best_perfect_count = count
            row["parabible_perfect_form"] = best_perfect_form
            row["parabible_perfect_aux"] = best_perfect_aux
            row["parabible_perfect_found_variant"] = best_perfect_variant
            if best_perfect:
                row["parabible_perfect_match_ref"] = best_perfect["ref"]
                row["parabible_perfect_match_avar"] = best_perfect["avar"]
                row["parabible_perfect_match_russian"] = best_perfect["russian"]
                row["parabible_perfect_match_source"] = "Parabible mini-corpus: Avar 468 + Russian 1055"
                row["parabible_perfect_match_count"] = str(best_perfect_count)
                if not example:
                    matched += 1
                    row["parabible_match_form"] = f"{best_perfect_form} {best_perfect_aux}".strip()
                    row["parabible_match_tense"] = f"perfect:{best_perfect_variant}" if best_perfect_variant else "perfect"
                    row["parabible_match_ref"] = best_perfect["ref"]
                    row["parabible_match_avar"] = best_perfect["avar"]
                    row["parabible_match_russian"] = best_perfect["russian"]
                    row["parabible_match_source"] = "Parabible mini-corpus: Avar 468 + Russian 1055"
                    row["parabible_match_count"] = str(best_perfect_count)
                    example = best_perfect
            else:
                row["parabible_perfect_match_ref"] = ""
                row["parabible_perfect_match_avar"] = ""
                row["parabible_perfect_match_russian"] = ""
                row["parabible_perfect_match_source"] = ""
                row["parabible_perfect_match_count"] = "0"

            best_pluperfect = None
            best_pluperfect_form = ""
            best_pluperfect_aux = ""
            best_pluperfect_variant = ""
            best_pluperfect_count = 0
            if not example and perfect_forms:
                for suffix_name, form_variant in perfect_forms:
                    ex, found_form, found_aux, count = find_best_bigram_example_variants(
                        [form_variant], pluperfect_auxes, verses, bigram_index
                    )
                    if ex and (best_pluperfect is None or verse_score(ex) > verse_score(best_pluperfect)):
                        best_pluperfect = ex
                        best_pluperfect_form = found_form
                        best_pluperfect_aux = found_aux
                        best_pluperfect_variant = suffix_name
                        best_pluperfect_count = count
            row["parabible_pluperfect_form"] = best_pluperfect_form
            row["parabible_pluperfect_aux"] = best_pluperfect_aux
            row["parabible_pluperfect_found_variant"] = best_pluperfect_variant
            if best_pluperfect:
                row["parabible_pluperfect_match_ref"] = best_pluperfect["ref"]
                row["parabible_pluperfect_match_avar"] = best_pluperfect["avar"]
                row["parabible_pluperfect_match_russian"] = best_pluperfect["russian"]
                row["parabible_pluperfect_match_source"] = "Parabible mini-corpus: Avar 468 + Russian 1055"
                row["parabible_pluperfect_match_count"] = str(best_pluperfect_count)
                if not example:
                    matched += 1
                    row["parabible_match_form"] = f"{best_pluperfect_form} {best_pluperfect_aux}".strip()
                    row["parabible_match_tense"] = f"pluperfect:{best_pluperfect_variant}" if best_pluperfect_variant else "pluperfect"
                    row["parabible_match_ref"] = best_pluperfect["ref"]
                    row["parabible_match_avar"] = best_pluperfect["avar"]
                    row["parabible_match_russian"] = best_pluperfect["russian"]
                    row["parabible_match_source"] = "Parabible mini-corpus: Avar 468 + Russian 1055"
                    row["parabible_match_count"] = str(best_pluperfect_count)
            else:
                row["parabible_pluperfect_match_ref"] = ""
                row["parabible_pluperfect_match_avar"] = ""
                row["parabible_pluperfect_match_russian"] = ""
                row["parabible_pluperfect_match_source"] = ""
                row["parabible_pluperfect_match_count"] = "0"

            compound_participles = compound_participle_variants(aorist_form)
            compound_present_aux = {"й": "йуго", "в": "вуго", "б": "буго", "р": "руго"}
            compound_past_aux = {"й": "йук1ана", "в": "вук1ана", "б": "бук1ана", "р": "рук1ана"}
            compound_future_aux = {"й": "йук1ина", "в": "вук1ина", "б": "бук1ина", "р": "рук1ина"}

            for prefix, aux_map in [
                ("parabible_compound_present", compound_present_aux),
                ("parabible_compound_past", compound_past_aux),
                ("parabible_compound_future", compound_future_aux),
            ]:
                row[f"{prefix}_form"] = ""
                row[f"{prefix}_aux"] = ""
                row[f"{prefix}_marker"] = ""
                row[f"{prefix}_match_ref"] = ""
                row[f"{prefix}_match_avar"] = ""
                row[f"{prefix}_match_russian"] = ""
                row[f"{prefix}_match_source"] = ""
                row[f"{prefix}_match_count"] = "0"

            if not example and compound_participles:
                for tense_name, prefix, aux_map in [
                    ("compound_present", "parabible_compound_present", compound_present_aux),
                    ("compound_past", "parabible_compound_past", compound_past_aux),
                    ("compound_future", "parabible_compound_future", compound_future_aux),
                ]:
                    ex, found_form, found_aux, found_marker, count = find_best_compound_example(
                        compound_participles, aux_map, verses, bigram_index
                    )
                    if ex:
                        row[f"{prefix}_form"] = found_form
                        row[f"{prefix}_aux"] = found_aux
                        row[f"{prefix}_marker"] = found_marker
                        row[f"{prefix}_match_ref"] = ex["ref"]
                        row[f"{prefix}_match_avar"] = ex["avar"]
                        row[f"{prefix}_match_russian"] = ex["russian"]
                        row[f"{prefix}_match_source"] = "Parabible mini-corpus: Avar 468 + Russian 1055"
                        row[f"{prefix}_match_count"] = str(count)
                        if not example:
                            matched += 1
                            row["parabible_match_form"] = f"{found_form} {found_aux}".strip()
                            row["parabible_match_tense"] = tense_name
                            row["parabible_match_ref"] = ex["ref"]
                            row["parabible_match_avar"] = ex["avar"]
                            row["parabible_match_russian"] = ex["russian"]
                            row["parabible_match_source"] = "Parabible mini-corpus: Avar 468 + Russian 1055"
                            row["parabible_match_count"] = str(count)
                            example = ex
                            break

            rows.append(row)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {out_csv}")
    print(f"Matched {matched} / {len(rows)} rows")


if __name__ == "__main__":
    main()
