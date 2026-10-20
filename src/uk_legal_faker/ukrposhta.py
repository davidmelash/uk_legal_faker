"""Build the Ukrposhta address table on this machine (`uk-legal-faker data ukrposhta`).

The directory of postal addresses of Ukrposhta («Довідник поштових адрес», houses.zip on ukrposhta.ua, linked from
index.ukrposhta.ua/find-post-index) lists 25,000+ settlements with their streets, postal indexes and house numbers -
three times the settlements of the bundled OpenStreetMap table. It carries no open licence, so it is not bundled: this
module downloads it and keeps a reduced table (a few house numbers per street) in the cache directory, where the
address generator finds it.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import time
import urllib.request
import zipfile
from pathlib import Path

from uk_legal_faker._data import ADDRESS_COLUMNS, cache_dir

URL = "https://www.ukrposhta.ua/files/shares/out/houses.zip"
SETTLEMENT_TYPES = {"м.", "с.", "с-ще"}
# street types as the directory writes them; the rest (хутір, урочище, присілок, …) are not streets
STREET_TYPES = {"вул.", "пров.", "просп.", "бульв.", "пл.", "проїзд", "узвіз", "майдан", "шосе", "тупик", "в’їзд", "м-р", "кв-л"}
HOUSES_KEPT = 8
_STREET_NAME = re.compile(r"[А-ЯІЇЄҐ0-9][А-ЯІЇЄҐа-яіїєґ0-9'’ʼ.\- ]{1,44}")
_HOUSE = re.compile(r"\d{1,3}(?:[-/]?[А-ЯІЇЄҐ]|/\d{1,3})?")
_TITLES = {"святого", "святої", "князя", "княгині", "гетьмана", "академіка", "генерала", "маршала", "героя", "отця",
           "митрополита", "професора", "полковника", "короля", "королеви", "патріарха", "єпископа", "лікаря", "імені"}


def _name_first(street: str, morph) -> str:
    """«Хмельницького Богдана» -> «Богдана Хмельницького»: the directory lists some streets surname first."""
    toks = street.split()
    if len(toks) != 2 or toks[0].lower() in _TITLES:
        return street
    surname, name = toks
    is_name = lambda w: any("Name" in p.tag for p in morph.parse(w))  # noqa: E731
    is_surname = any("Surn" in p.tag for p in morph.parse(surname)) or surname.endswith(("ського", "цького", "зького"))
    return f"{name} {surname}" if is_name(name) and not is_name(surname) and is_surname else street


def build(source: Path | None = None, force: bool = False, log=print) -> Path:
    """Download houses.zip (or read `source`, a copy on disk) and write ukrposhta.tsv.gz to the cache directory."""
    import pymorphy3

    out = cache_dir() / "ukrposhta.tsv.gz"
    if out.exists() and not force:
        log(f"{out} exists (use --force to rebuild)")
        return out
    if source is None:
        log(f"downloading {URL} …")
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (uk-legal-faker)"})
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
    else:
        raw = Path(source).expanduser().read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode("cp1251")
    morph = pymorphy3.MorphAnalyzer(lang="uk")
    fixed: dict[str, str] = {}
    rows, total = [], 0
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    next(reader)
    for row in reader:
        if len(row) < 8:
            continue
        total += 1
        region, old, new, _community, np_full, zip_code, street_full, houses = (c.strip() for c in row[:8])
        np_type, _, np_name = np_full.partition(" ")
        st_type, _, street = street_full.partition(" ")
        nums = [h for h in houses.split(",") if _HOUSE.fullmatch(h)]
        if np_type not in SETTLEMENT_TYPES or st_type not in STREET_TYPES or not nums or not re.fullmatch(r"\d{5}", zip_code) \
                or not _STREET_NAME.fullmatch(street) or not np_name:
            continue
        if street not in fixed:
            fixed[street] = _name_first(street, morph)
        step = max(1, len(nums) // HOUSES_KEPT)  # evenly spread over the street, so both small and large numbers stay
        rows.append((region, old, new, np_type, np_name, zip_code, st_type, fixed[street], ",".join(nums[::step][:HOUSES_KEPT]), ""))
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8", newline="") as f:
        f.write("\t".join(ADDRESS_COLUMNS) + "\n")
        for r in rows:
            f.write("\t".join(v.replace("\t", " ") for v in r) + "\n")
    meta = {"url": URL, "sha256": hashlib.sha256(raw).hexdigest(), "built": time.strftime("%Y-%m-%d"), "rows_source": total,
            "rows_kept": len(rows), "settlements": len({(r[0], r[2], r[3], r[4]) for r in rows})}
    out.with_name("ukrposhta.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"wrote {out}: {meta['rows_kept']} streets of {meta['settlements']} settlements")
    return out
