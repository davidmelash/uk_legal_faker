"""Fill a corpus of pseudonymized decisions and write character spans and token-level BIO tags.

    python examples/build_ner_dataset.py pseudonymized.jsonl train.jsonl --versions 2
    python examples/build_ner_dataset.py --templates out.jsonl          # the bundled decisions, as a demo

The input has one JSON object per line with `id` and `text` (a decision with ОСОБА_1 / АДРЕСА_1 / НОМЕР_1 /
ІНФОРМАЦІЯ_1 placeholders). Each output line carries `tokens` and `tags`. Masked values (doubtful kind) get the tag
«IGNORE», and a training script should drop them from the loss.
"""
from __future__ import annotations

import argparse
import json
import re

from uk_legal_faker import FilledDocument, LegalFaker

TOKEN = re.compile(r"\w+(?:[-'’ʼ]\w+)*|[^\w\s]")


def bio(doc: FilledDocument) -> tuple[list[str], list[str]]:
    """Whitespace-and-punctuation tokens of the filled text and their B-/I- tags."""
    tokens, tags = [], []
    spans = sorted(doc.entities, key=lambda e: e.start)
    k = 0
    for m in TOKEN.finditer(doc.text):
        while k < len(spans) and spans[k].end <= m.start():
            k += 1
        e = spans[k] if k < len(spans) and spans[k].start < m.end() else None
        tokens.append(m.group())
        if e is None:
            tags.append("O")
        elif e.masked:
            tags.append("IGNORE")
        else:
            tags.append(("B-" if m.start() <= e.start else "I-") + e.label)
    return tokens, tags


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", help="JSONL with id and text")
    ap.add_argument("output")
    ap.add_argument("--templates", action="store_true", help="use the bundled decisions instead of an input file")
    ap.add_argument("--versions", type=int, default=1, help="fill every decision this many times")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    fake = LegalFaker(seed=a.seed)
    if a.templates:
        rows = fake.templates()
    elif a.input:
        with open(a.input, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    else:
        ap.error("give an input file or --templates")
    n = 0
    with open(a.output, "w", encoding="utf-8") as out:
        for row in rows:
            for version in range(1, a.versions + 1):
                doc = fake.fill(row["text"], doc_id=str(row["id"]), kind=row.get("kind"), version=version)
                tokens, tags = bio(doc)
                out.write(json.dumps({"id": f"{row['id']}-v{version}", **doc.to_dict(), "tokens": tokens, "tags": tags}, ensure_ascii=False) + "\n")
                n += 1
    print(f"wrote {n} documents to {a.output}")


if __name__ == "__main__":
    main()
