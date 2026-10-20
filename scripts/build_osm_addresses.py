#!/usr/bin/env python3
"""Build src/uk_legal_faker/data/addresses_osm.tsv.gz from the OpenStreetMap extract of Ukraine.

    pip install osmium shapely
    python scripts/build_osm_addresses.py                               # downloads ~880 MB from Geofabrik
    python scripts/build_osm_addresses.py --pbf ~/Downloads/ukraine-latest.osm.pbf

Every address object (node, building way or multipolygon with `addr:housenumber` and `addr:street`) is placed by its
coordinates into a region, a district, a settlement and, inside big cities, a city district; the table keeps up to 8
house numbers per street, in the layout of the Ukrposhta directory plus the district of a city.

Data © OpenStreetMap contributors, Open Database License 1.0 (https://www.openstreetmap.org/copyright).
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import math
import re
import time
import urllib.request
from collections import Counter
from pathlib import Path

PBF_URL = "https://download.geofabrik.de/europe/ukraine-latest.osm.pbf"
OUT = Path(__file__).resolve().parents[1] / "src" / "uk_legal_faker" / "data" / "addresses_osm.tsv.gz"

log = logging.getLogger("build_osm_addresses")

# OSM street type word -> the abbreviation used in the Ukrposhta directory (uk_legal_faker.addresses.STREET_TYPES)
STREET_WORDS = {
    "вулиця": "вул.", "вул.": "вул.", "провулок": "пров.", "пров.": "пров.", "проспект": "просп.", "просп.": "просп.",
    "пр-т": "просп.", "бульвар": "бульв.", "бульв.": "бульв.", "б-р": "бульв.", "площа": "пл.", "пл.": "пл.",
    "проїзд": "проїзд", "узвіз": "узвіз", "майдан": "майдан", "шосе": "шосе", "тупик": "тупик", "в'їзд": "в’їзд",
    "мікрорайон": "м-р", "м-н": "м-р", "квартал": "кв-л",
}
# Russian spellings: letters, type words and adjective endings («Советская», «Лесной», «Новый») that Ukrainian lacks
_RUSSIAN = re.compile(r"[ыэъё]|\b(?:улица|ул\.|переулок|пер\.|площадь|проезд|шоссе)\b|(?:ая|яя|ый|ой)\b", re.I)
_NAME = re.compile(r"[А-ЯІЇЄҐ0-9][А-ЯІЇЄҐа-яіїєґ0-9'’ʼ.\- ]{1,44}")
_HOUSE = re.compile(r"\d{1,3}(?:[-/]?[А-ЯІЇЄҐ]|/\d{1,3})?")
PLACE_TYPES = {"city": "м.", "town": "м.", "village": "с.", "hamlet": "с."}
COLUMNS = ("region", "district_old", "district_new", "np_type", "np", "zip", "st_type", "street", "houses", "city_district")
HOUSES_KEPT = 8
NEAREST_KM = 3.0  # an address outside every settlement outline belongs to the closest settlement point within this distance


def _apostrophe(s: str) -> str:
    return s.replace("’", "'").replace("ʼ", "'").replace("`", "'")


def parse_street(raw: str) -> tuple[str, str] | None:
    """`вулиця Богдана Хмельницького` / `Садова вулиця` / `Хрещатик` -> (`вул.`, name); None for what is not a
    Ukrainian street name."""
    raw = " ".join(raw.split())
    if not raw or _RUSSIAN.search(raw):
        return None
    words = raw.split(" ")
    kinds = [i for i, w in enumerate(words) if _apostrophe(w).lower() in STREET_WORDS]
    if kinds and len(words) > 1:  # the type word stands first, last or, rarely, in the middle («1-й провулок Шевченка»)
        i = kinds[0]
        st_type, name = STREET_WORDS[_apostrophe(words[i]).lower()], " ".join(words[:i] + words[i + 1:])
    elif raw[0].islower():
        return None  # another kind of way («набережна …», «алея …») that the generator has no wording for
    else:
        st_type, name = "вул.", raw  # a bare name is a street
    name = name[:1].upper() + name[1:]
    return (st_type, name) if _NAME.fullmatch(name) and not name.isdigit() else None


def norm_house(raw: str) -> str | None:
    """`12-а`, `12 А`, `12/3` -> `12-А`, `12А`, `12/3`; None for ranges, descriptions and the like."""
    h = raw.replace(" ", "").upper()
    return h if _HOUSE.fullmatch(h) else None


def region_name(name: str) -> str | None:
    """`Київська область` -> `Київська`, `Київ` -> `Київ`; None for what the generator has no rules for (Crimea)."""
    if name == "Київ":
        return name
    return name[: -len(" область")] if name.endswith(" область") else None


def district_name(name: str) -> str | None:
    """`Броварський район` -> `Броварський`."""
    return name[: -len(" район")] if name.endswith(" район") else None


def _house_key(h: str) -> tuple[int, str]:
    return int(re.match(r"\d+", h).group()), h


def build(pbf: Path, out: Path) -> dict:
    """Read the extract once, place every address by its coordinates, write one row per street of a settlement."""
    import numpy as np
    import osmium
    import shapely
    from shapely import STRtree

    t0 = time.time()
    wkb = osmium.geom.WKBFactory()
    xs, ys, addr = [], [], []  # coordinates and (street type, street, house, postcode) of every address object
    shapes = {"region": [], "district": [], "settlement": [], "city_district": []}  # (name or (type, name), geometry)
    points = []  # settlements mapped as a point only: (lon, lat, type, name)
    stats: Counter = Counter()

    def uk(tags) -> str:
        return (tags.get("name:uk") or tags.get("name") or "").strip()

    def geometry(area):
        try:
            return shapely.from_wkb(wkb.create_multipolygon(area))
        except Exception:  # an outline that does not close
            stats["broken_outline"] += 1
            return None

    fp = (osmium.FileProcessor(str(pbf)).with_locations().with_areas(osmium.filter.KeyFilter("admin_level", "place", "addr:housenumber"))
          .with_filter(osmium.filter.KeyFilter("addr:housenumber", "admin_level", "place")))
    for o in fp:
        t = o.tags
        if o.is_area() and o.from_way() and "place" not in t and "admin_level" not in t:
            continue  # a building: the same closed way is read as a way below
        if o.is_area():
            name, level, place = uk(t), t.get("admin_level"), t.get("place")
            admin = t.get("boundary") == "administrative"
            if admin and level == "4" and region_name(name):
                kind, value = "region", region_name(name)
            elif admin and level == "6" and district_name(name):
                kind, value = "district", district_name(name)
            elif admin and level in ("8", "9", "10") and district_name(name) and "," not in name:
                kind, value = "city_district", district_name(name)
            elif place in PLACE_TYPES and name and not _RUSSIAN.search(name):
                kind, value = "settlement", (PLACE_TYPES[place], name)
            else:
                kind = None
            if kind:
                g = geometry(o)
                if g is not None:
                    shapes[kind].append((value, g))
            if o.from_way() or "addr:housenumber" not in t:
                continue  # a building way is read as a way below; a multipolygon building only arrives as an area
        elif o.is_node() and t.get("place") in PLACE_TYPES and uk(t) and not _RUSSIAN.search(uk(t)):
            points.append((o.location.lon, o.location.lat, PLACE_TYPES[t["place"]], uk(t)))
        if "addr:housenumber" not in t or "addr:street" not in t:
            continue
        stats["address_objects"] += 1
        street, house = parse_street(t["addr:street"]), norm_house(t["addr:housenumber"])
        if not street or not house:
            stats["skipped_street" if not street else "skipped_house"] += 1
            continue
        try:
            loc = o.location if o.is_node() else o.nodes[0].location if o.is_way() else next(iter(next(iter(o.outer_rings())))).location
            xs.append(loc.lon)
            ys.append(loc.lat)
        except Exception:  # a way whose nodes are outside the extract
            stats["no_coordinates"] += 1
            continue
        code = t.get("addr:postcode", "")
        addr.append((*street, house, code if re.fullmatch(r"\d{5}", code) else ""))
    log.info("osm: read %d addresses, %s outlines, %d settlement points in %.0fs", len(addr),
             {k: len(v) for k, v in shapes.items()}, len(points), time.time() - t0)

    pts = shapely.points(np.array(xs), np.array(ys))

    def within(kind: str, smallest: bool = False) -> list:
        """For every address the value of the outline that contains it (the smallest one when outlines nest)."""
        values, geoms = [v for v, _ in shapes[kind]], [g for _, g in shapes[kind]]
        found = [None] * len(addr)
        if not geoms:
            return found
        size = shapely.area(geoms) if smallest else None
        best = {}
        for i, j in zip(*STRtree(geoms).query(pts, predicate="within")):
            if i not in best or (smallest and size[j] < size[best[i]]):
                best[i] = j
        for i, j in best.items():
            found[i] = values[j]
        return found

    region, district, city_district = within("region"), within("district"), within("city_district")
    settlement = within("settlement", smallest=True)
    stats["in_settlement_outline"] = sum(s is not None for s in settlement)
    # the rest: the closest settlement point; longitudes are shrunk so that a degree is about the same length both ways
    shrink = math.cos(math.radians(48.5))
    if points:
        todo = [i for i, s in enumerate(settlement) if s is None]
        near = STRtree(shapely.points(np.array([p[0] for p in points]) * shrink, np.array([p[1] for p in points])))
        q = shapely.points(np.array([xs[i] for i in todo]) * shrink, np.array([ys[i] for i in todo]))
        for a, b in zip(*near.query_nearest(q, max_distance=NEAREST_KM / 111.0)):
            settlement[todo[a]] = (points[b][2], points[b][3])
            stats["by_closest_point"] += 1

    groups: dict[tuple, tuple[set, Counter]] = {}
    for i, (st_type, street, house, code) in enumerate(addr):
        if region[i] == "Київ":
            settlement[i], district[i] = ("м.", "Київ"), "Київ"  # the Ukrposhta directory writes the city as its own district
        if not region[i] or not settlement[i] or not district[i]:
            stats["unplaced"] += 1
            continue
        np_type, np_name = settlement[i]
        key = (region[i], district[i], np_type, np_name, city_district[i] if np_type == "м." else None, st_type, street)
        houses, codes = groups.setdefault(key, (set(), Counter()))
        houses.add(house)
        if code:
            codes[code] += 1
    cols = {c: [] for c in COLUMNS}
    for (reg, dist, np_type, np_name, cd, st_type, street), (houses, codes) in sorted(groups.items(), key=lambda kv: tuple(x or "" for x in kv[0])):
        nums = sorted(houses, key=_house_key)
        step = max(1, len(nums) // HOUSES_KEPT)
        row = (reg, "", dist, np_type, np_name, codes.most_common(1)[0][0] if codes else "", st_type, street,
               ",".join(nums[::step][:HOUSES_KEPT]), cd or "")
        for c, v in zip(COLUMNS, row):
            cols[c].append(v)
    with gzip.open(out, "wt", encoding="utf-8", newline="") as f:
        f.write("\t".join(COLUMNS) + "\n")
        for row in zip(*(cols[c] for c in COLUMNS)):
            f.write("\t".join(v.replace("\t", " ") for v in row) + "\n")
    meta = {"rows": len(cols["np"]), "addresses_used": len(addr) - stats["unplaced"],
            "settlements": len(set(zip(cols["region"], cols["district_new"], cols["np_type"], cols["np"]))),
            "rows_with_city_district": sum(bool(c) for c in cols["city_district"]),
            "rows_with_index": sum(bool(z) for z in cols["zip"]), **dict(stats), "seconds": round(time.time() - t0)}
    log.info("osm: %s", meta)
    return meta


def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (uk-legal-faker)"})
    with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
        total, done, t0 = int(r.headers.get("Content-Length", 0)), 0, time.time()
        while chunk := r.read(1 << 22):
            f.write(chunk)
            done += len(chunk)
            print(f"\r{path.name}: {done >> 20} / {total >> 20} MB, {time.time() - t0:.0f}s", end="", flush=True)
    print()
    part.rename(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pbf", default=None, help="an extract already on disk (default: download it next to the output)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = Path(a.out)
    pbf = Path(a.pbf).expanduser() if a.pbf else out.parent / "ukraine-latest.osm.pbf"
    if not pbf.exists():
        download(PBF_URL, pbf)
    meta = {"url": PBF_URL, "file": pbf.name, "file_date": time.strftime("%Y-%m-%d", time.localtime(pbf.stat().st_mtime)),
            "licence": "© OpenStreetMap contributors, ODbL 1.0", **build(pbf, out)}
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
