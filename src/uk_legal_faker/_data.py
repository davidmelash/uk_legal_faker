"""Loading the data files: the ones bundled with the package and the optional ones built on the user's machine."""
from __future__ import annotations

import csv
import gzip
import io
import json
import os
from collections.abc import Iterator
from functools import lru_cache
from importlib import resources
from pathlib import Path

# address table columns, shared by every address source (see docs/data.md)
ADDRESS_COLUMNS = ("region", "district_old", "district_new", "np_type", "np", "zip", "st_type", "street", "houses",
                   "city_district")


def cache_dir() -> Path:
    """Where optional tables built on this machine live: $UK_LEGAL_FAKER_HOME, else ~/.cache/uk-legal-faker."""
    home = os.environ.get("UK_LEGAL_FAKER_HOME")
    if home:
        return Path(home).expanduser()
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".cache") / "uk-legal-faker"


def _open_bundled(name: str) -> io.TextIOWrapper:
    raw = resources.files("uk_legal_faker").joinpath("data", name).open("rb")
    return io.TextIOWrapper(gzip.GzipFile(fileobj=raw), encoding="utf-8", newline="")


@lru_cache(maxsize=1)
def name_pools() -> dict[str, list[tuple[str, float]]]:
    """First names, patronymics (by gender) and surnames with their weights."""
    with _open_bundled("names.json.gz") as f:
        return {k: [(n, w) for n, w in v] for k, v in json.load(f).items()}


def _read_tsv(f) -> Iterator[tuple[str, ...]]:
    reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
    header = next(reader)
    at = [header.index(c) if c in header else None for c in ADDRESS_COLUMNS]
    for row in reader:
        yield tuple(row[i] if i is not None else "" for i in at)


def address_rows(source: str) -> list[tuple[str, ...]]:
    """Rows of an address table: «osm» is bundled, «ukrposhta» is built by `uk-legal-faker data ukrposhta`, anything
    else is read as a path to a TSV file (gzipped or not) with the ADDRESS_COLUMNS header."""
    if source == "osm":
        with _open_bundled("addresses_osm.tsv.gz") as f:
            return list(_read_tsv(f))
    path = cache_dir() / "ukrposhta.tsv.gz" if source == "ukrposhta" else Path(source).expanduser()
    if not path.exists():
        hint = "run `uk-legal-faker data ukrposhta` to build it" if source == "ukrposhta" else "no such file"
        raise FileNotFoundError(f"address table {path} is missing: {hint}")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as f:
        return list(_read_tsv(f))


def ukrposhta_available() -> bool:
    return (cache_dir() / "ukrposhta.tsv.gz").exists()


@lru_cache(maxsize=1)
def decisions() -> tuple[dict, ...]:
    """Pseudonymized court decisions used as templates by LegalFaker.court_decision()."""
    with _open_bundled("decisions.jsonl.gz") as f:
        return tuple(json.loads(line) for line in f if line.strip())


def load_org_names(source: str | Path | dict) -> dict[tuple[str, str], list[str]]:
    """Real organisation names for the institution generator: a mapping (source, kind) -> names, or a TSV / CSV file
    with the columns `source`, `kind`, `name`. See docs/data.md for the keys the generator reads."""
    if isinstance(source, dict):
        return {tuple(k) if not isinstance(k, tuple) else k: list(v) for k, v in source.items()}  # type: ignore[misc]
    path = Path(source).expanduser()
    opener = gzip.open if path.suffix == ".gz" else open
    delimiter = "," if ".csv" in path.suffixes else "\t"
    out: dict[tuple[str, str], list[str]] = {}
    with opener(path, "rt", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter=delimiter):
            out.setdefault((row["source"], row["kind"]), []).append(row["name"])
    return {k: sorted(v) for k, v in out.items()}
