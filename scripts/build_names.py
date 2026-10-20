#!/usr/bin/env python3
"""Build src/uk_legal_faker/data/names.json.gz from the frequency dictionaries of lang-uk/name_freq_dict_uk (GPL-3.0).

    python scripts/build_names.py                       # download the CSV files and build
    python scripts/build_names.py --from-json old.json  # clean an existing {key: [[name, weight], …]} file again

Kept: the 400 most frequent first names and patronymics of each gender and the 2,500 most frequent surnames, with the
square root of their corpus frequency as the weight (so that a few public figures do not dominate). Dropped: names
with digits or punctuation, and first names that are no first names - surnames, place names and nouns that the
corpus counted as names («Бойко», «Житомир», «Сокіл»), the invented names of fiction («Гуляйвітер») and names of the
other gender («Русудан» among the men).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import urllib.request
from pathlib import Path

RAW = "https://raw.githubusercontent.com/lang-uk/name_freq_dict_uk/master/generated/"
FILES = {"male_first": "male_fname_freq_dict.csv", "female_first": "female_fname_freq_dict.csv",
         "male_patr": "male_pname_freq_dict.csv", "female_patr": "female_pname_freq_dict.csv", "surname": "lname_freq_dict.csv"}
TOP = {"surname": 2500}
TOP_DEFAULT = 400
BAD_CHARS = set("*_[]()/\\\"0123456789")
OUT = Path(__file__).resolve().parents[1] / "src" / "uk_legal_faker" / "data" / "names.json.gz"
# first names the dictionary of pymorphy3 does not tag as a first name, but which are real and common enough
KEEP_UNTAGGED = {"male_first": {"Володимир", "Богдан", "Анісій", "Пимен", "Флор", "Вукол", "Любим", "Тихомир", "Далібор", "Драган", "Ждан"},
                 "female_first": {"Віта", "Лада", "Текля", "Віола", "Домаха", "Ракель", "Аполлонія", "Агнія", "Юдита", "Єпистимія", "Васса"}}
# names of one gender that the corpus also listed under the other
WRONG_GENDER = {"male_first": {"Русудан"}}


def download() -> dict[str, list[tuple[str, float]]]:
    data = {}
    for key, fn in FILES.items():
        with urllib.request.urlopen(RAW + fn, timeout=60) as r:
            rows = csv.DictReader(io.StringIO(r.read().decode("utf-8")))
            items = [(row["name"].strip(), float(row["freq_in_corpus"])) for row in rows]
        items = [(n, f) for n, f in items if n and not set(n) & BAD_CHARS and n[0].isupper() and len(n) >= 3]
        items = sorted(items, key=lambda x: -x[1])[: TOP.get(key, TOP_DEFAULT)]
        data[key] = [(n, math.sqrt(f) + 1e-6) for n, f in items]
        print(f"{key}: {len(data[key])}")
    return data


def clean(data: dict[str, list[tuple[str, float]]]) -> dict[str, list[tuple[str, float]]]:
    import pymorphy3

    morph = pymorphy3.MorphAnalyzer(lang="uk")
    out = dict(data)
    for key in ("male_first", "female_first"):
        kept = [(n, w) for n, w in data[key]
                if n not in WRONG_GENDER.get(key, ())
                and (n in KEEP_UNTAGGED[key] or any("Name" in p.tag.grammemes for p in morph.parse(n)))]
        print(f"{key}: {len(data[key])} -> {len(kept)}")
        out[key] = kept
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-json", default=None, help="clean an existing names.json instead of downloading")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.from_json:
        opener = gzip.open if a.from_json.endswith(".gz") else open
        with opener(a.from_json, "rt", encoding="utf-8") as f:
            data = {k: [(n, w) for n, w in v] for k, v in json.load(f).items()}
    else:
        data = download()
    data = clean(data)
    with gzip.open(a.out, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
