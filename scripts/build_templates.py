#!/usr/bin/env python3
"""Build src/uk_legal_faker/data/decisions.jsonl.gz: pseudonymized court decisions that LegalFaker.court_decision fills.

    pip install pyarrow
    python scripts/build_templates.py --check   # refetch the texts of the bundled ids and compare
    python scripts/build_templates.py           # a fresh selection by the rules below

Source: the Hugging Face dataset lang-uk/court-decisions-uk (MIT), decisions of 2024 from the Unified State Register of
Court Decisions. Rules: 1,500-6,000 characters after normalization, at least three of the four placeholder types, no
malformed placeholders; a quota per kind of decision (QUOTA), the decisions with the smallest SHA-1 of their id. The
250 decisions of `250-deanonymized-court-cases.parquet` (an evaluation set built from the same register) and other
decisions of their cases are left out, so that the templates never overlap it.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from uk_legal_faker.document import find_placeholders, normalize  # noqa: E402

HF = "https://huggingface.co/datasets/lang-uk/court-decisions-uk/resolve/main/"
FILES = {"vs5k": "2024-5K-supreme-court-decisions-deduplicated.parquet", "edrsr": "2024-court-decisions.parquet"}
EXCLUDE = "250-deanonymized-court-cases.parquet"
OUT = Path(__file__).resolve().parents[1] / "src" / "uk_legal_faker" / "data" / "decisions.jsonl.gz"
QUOTA = {"ВС": 24, "ЦПК": 10, "КАС": 8, "військові": 8, "КПК": 6, "ГПК": 4}
MIN_LEN, MAX_LEN = 1500, 6000
_ODD = re.compile(r"\b(?:ІМЕІ\w*|ОСОБИ|ОСОБ)_\d+")
_CASE = re.compile(r"[сcС]прав[аи]\s*№\s*(\d[\w/\-.]*\w)")
_CODES = {"КУпАП": re.compile(r"КУпАП|адміністративн\w+\s+правопорушенн"), "КПК": re.compile(r"\bКПК\b|кримінальн\w+\s+провадженн"),
          "КАС": re.compile(r"\bКАС\b|адміністративн\w+\s+судочинств"), "ЦПК": re.compile(r"\bЦПК\b|цивільн\w+\s+(?:справ|судочинств)"),
          "ГПК": re.compile(r"\bГПК\b|господарськ\w+\s+суд")}
_MILITARY = re.compile(r"військов\w+\s+частин\w*\s+(?:№\s*)?НОМЕР_\d+")


def doc_kind(text: str) -> str:
    """Supreme Court / a serviceman's case / the procedural code the decision cites most."""
    if "Верховн" in text[:600]:
        return "ВС"
    if _MILITARY.search(text):
        return "військові"
    score = {k: len(rx.findall(text)) for k, rx in _CODES.items()}
    return max(score, key=score.get) if max(score.values()) else "інше"


def fetch(name: str, cache: Path) -> Path:
    path = cache / name
    if not path.exists():
        print(f"downloading {name} …")
        cache.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(HF + name, path)
    return path


def read(path: Path, column: str = "text"):
    import pyarrow.parquet as pq

    for batch in pq.ParquetFile(path).iter_batches(batch_size=2000, columns=["id", column]):
        yield from zip(map(str, batch.column("id").to_pylist()), batch.column(column).to_pylist())


def candidates(cache: Path):
    excluded_ids, excluded_cases = set(), set()
    for doc_id, text in read(fetch(EXCLUDE, cache), "original_text"):
        excluded_ids.add(doc_id)
        excluded_cases.update(_CASE.findall(text[:600]))
    for name in FILES.values():
        for doc_id, raw in read(fetch(name, cache)):
            text = normalize(raw)
            if doc_id in excluded_ids or set(_CASE.findall(text[:600])) & excluded_cases:
                continue
            yield {"id": doc_id, "kind": doc_kind(text), "case": next(iter(_CASE.findall(text[:600])), None),
                   "source": f"lang-uk/court-decisions-uk ({name})", "text": text}


def usable(doc: dict) -> bool:
    types = {p["type"] for p in find_placeholders(doc["text"])}
    return MIN_LEN <= len(doc["text"]) <= MAX_LEN and len(types) >= 3 and not _ODD.search(doc["text"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "uk-legal-faker" / "hf"), help="where the parquet files go")
    ap.add_argument("--check", action="store_true", help="compare the bundled templates with the source texts")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    cache = Path(a.cache).expanduser()
    if a.check:
        with gzip.open(OUT, "rt", encoding="utf-8") as f:
            bundled = {d["id"]: d for d in map(json.loads, f)}
        found = {d["id"]: d for d in candidates(cache) if d["id"] in bundled}
        same = sum(found.get(i, {}).get("text") == d["text"] for i, d in bundled.items())
        print(f"{same} of {len(bundled)} bundled templates match the source text")
        return
    pools: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for doc in candidates(cache):
        key = doc["text"][:300]  # near-identical copies of one decision
        if doc["kind"] in QUOTA and usable(doc) and key not in seen:
            seen.add(key)
            pools.setdefault(doc["kind"], []).append(doc)
    out = [d for kind, n in QUOTA.items() for d in sorted(pools.get(kind, []), key=lambda d: hashlib.sha1(d["id"].encode()).hexdigest())[:n]]
    with gzip.open(a.out, "wt", encoding="utf-8") as f:
        for d in out:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"wrote {len(out)} templates to {a.out}")


if __name__ == "__main__":
    main()
