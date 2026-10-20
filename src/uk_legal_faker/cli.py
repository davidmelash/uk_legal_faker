"""Command line: `uk-legal-faker --help`."""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

from uk_legal_faker import __version__
from uk_legal_faker.generator import LegalFaker

# what `uk-legal-faker generate` can write, and whether the method takes a grammatical case
GENERATORS = {
    "name": True, "address": False, "settlement": False, "rnokpp": False, "passport": False, "iban": False, "bank_card": False,
    "phone": False, "imei": False, "certificate_number": False, "military_unit_code": False, "vin": False, "license_plate": False,
    "enforcement_proceeding_number": False, "birth_date": False, "email": False, "url": False, "social_account": False,
    "military_unit": True, "military_unit_name": True, "military_body": True, "tck": True, "civil_body": True, "company": True,
    "company_name": False, "bank": False, "court": True, "prosecutors_office": True, "police_unit": True, "hospital": True,
}


def _open_out(path: str | None) -> contextlib.AbstractContextManager[TextIO]:
    """The output file, or stdout (left open)."""
    return open(path, "w", encoding="utf-8") if path and path != "-" else contextlib.nullcontext(sys.stdout)


def _read_docs(path: str, text_field: str, id_field: str) -> Iterator[tuple[str | None, str, dict]]:
    """(id, text, row) from a JSONL file (one object per line), or the whole of a plain-text file / stdin as one text."""
    f = sys.stdin if path == "-" else open(path, encoding="utf-8")
    with f:
        if path.endswith(".jsonl") or path.endswith(".ndjson"):
            for n, line in enumerate(f, 1):
                if line.strip():
                    row = json.loads(line)
                    if text_field not in row:
                        raise SystemExit(f"{path}:{n}: no field {text_field!r} (use --text-field)")
                    yield (str(row[id_field]) if id_field in row else None), row[text_field], row
        else:
            yield None, f.read(), {}


def _emit(doc, out: TextIO, fmt: str, extra: dict | None = None) -> None:
    if fmt == "text":
        out.write(doc.text.rstrip("\n") + "\n")
    elif fmt == "highlight":
        out.write(doc.highlight() + "\n\n")
    else:
        out.write(json.dumps({**(extra or {}), **doc.to_dict()}, ensure_ascii=False) + "\n")


def cmd_fill(a: argparse.Namespace) -> None:
    fake = LegalFaker(a.seed)
    with _open_out(a.output) as out:
        for doc_id, text, row in _read_docs(a.input, a.text_field, a.id_field):
            extra = {k: v for k, v in row.items() if k not in (a.text_field, "text", "annotations", "masks")} if a.keep_fields else None
            for version in range(1, a.versions + 1):
                doc = fake.fill(text, doc_id=doc_id, version=version, kind=row.get("kind"), normalize_text=not a.no_normalize)
                _emit(doc, out, a.format, extra)


def cmd_sample(a: argparse.Namespace) -> None:
    fake = LegalFaker(a.seed)
    with _open_out(a.output) as out:
        for _ in range(a.n):
            _emit(fake.court_decision(a.kind), out, a.format)


def cmd_generate(a: argparse.Namespace) -> None:
    fake = LegalFaker(a.seed)
    method = getattr(fake, a.what)
    kwargs = {"case": a.case} if a.case and GENERATORS[a.what] else {}
    if a.region and a.what in ("address", "settlement"):
        kwargs["region"] = a.region
    with _open_out(a.output) as out:
        for _ in range(a.n):
            out.write(f"{method(**kwargs)}\n")


def cmd_data(a: argparse.Namespace) -> None:
    from uk_legal_faker import ukrposhta

    ukrposhta.build(Path(a.source) if a.source else None, force=a.force)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="uk-legal-faker", description="Synthetic personal data for Ukrainian court decisions.")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser, formats: bool = True) -> None:
        p.add_argument("--seed", type=int, default=None, help="random seed (reproducible output)")
        p.add_argument("-o", "--output", default=None, help="output file (default: stdout)")
        if formats:
            p.add_argument("--format", choices=("jsonl", "text", "highlight"), default="jsonl",
                           help="jsonl: text + annotations; text: filled text only; highlight: entities marked in the text")

    p = sub.add_parser("fill", help="fill the placeholders of pseudonymized decisions",
                       description="Fill ОСОБА_n / АДРЕСА_n / НОМЕР_n / ІНФОРМАЦІЯ_n placeholders. INPUT is a .jsonl file (one "
                                   "decision per line), a text file or - for stdin.")
    p.add_argument("input")
    common(p)
    p.add_argument("--text-field", default="text", help="JSONL field with the pseudonymized text (default: text)")
    p.add_argument("--id-field", default="id", help="JSONL field with the document id; it makes each document's values reproducible")
    p.add_argument("--versions", type=int, default=1, help="fill every document this many times with other values")
    p.add_argument("--keep-fields", action="store_true", help="copy the other JSONL fields to the output")
    p.add_argument("--no-normalize", action="store_true", help="keep the register's spacing around placeholders")
    p.set_defaults(func=cmd_fill)

    p = sub.add_parser("sample", help="filled court decisions from the bundled templates")
    p.add_argument("-n", type=int, default=1, help="how many decisions")
    p.add_argument("--kind", default=None, help="ВС, ЦПК, КАС, військові, КПК or ГПК")
    common(p)
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("generate", help="single values: names, addresses, identifiers, bodies, …")
    p.add_argument("what", choices=sorted(GENERATORS))
    p.add_argument("-n", type=int, default=5, help="how many values")
    p.add_argument("--case", default=None, help="grammatical case for names and bodies: nomn, gent, datv, accs, ablt, loct")
    p.add_argument("--region", default=None, help="region of an address, e.g. Львівська (Київ for the city)")
    common(p, formats=False)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("data", help="build optional data tables on this machine")
    p.add_argument("table", choices=("ukrposhta",), help="ukrposhta: the postal address directory (25,000+ settlements)")
    p.add_argument("--source", default=None, help="a houses.zip already on disk (default: download it)")
    p.add_argument("--force", action="store_true", help="rebuild the table")
    p.set_defaults(func=cmd_data)

    a = ap.parse_args(argv)
    try:
        a.func(a)
    except (ValueError, FileNotFoundError) as e:
        raise SystemExit(f"uk-legal-faker: {e}") from None


if __name__ == "__main__":
    main()
