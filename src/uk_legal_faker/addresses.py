"""Synthetic Ukrainian addresses from address directories.

Every address is one row of a directory: settlement, district, street, postal index and a real house number belong
together. Two directories are known: OpenStreetMap (bundled, © OpenStreetMap contributors, ODbL) and the Ukrposhta
directory of postal addresses (optional, built on the user's machine by `uk-legal-faker data ukrposhta`). Where both
know a settlement, the Ukrposhta spelling, type and districts are kept and an address comes from an OpenStreetMap row
with probability P_OSM.

The region of an address follows the text it is written into (`doc_context`), and the style - word order,
abbreviations, «по вулиці …» - is chosen once per document.
"""
from __future__ import annotations

import random
from collections import Counter
from functools import lru_cache
from itertools import accumulate, product

import pymorphy3

from uk_legal_faker._data import address_rows, ukrposhta_available
from uk_legal_faker.orgs import inflect_phrase
from uk_legal_faker.region import CENTRES, KYIV, doc_places, doc_region

_morph = pymorphy3.MorphAnalyzer(lang="uk")
# directory street type -> (short, full word, locative of the full word)
STREET_TYPES = {
    "вул.": ("вул.", "вулиця", "вулиці"), "пров.": ("пров.", "провулок", "провулку"), "просп.": ("просп.", "проспект", "проспекті"),
    "бульв.": ("бульв.", "бульвар", "бульварі"), "пл.": ("пл.", "площа", "площі"), "проїзд": ("проїзд", "проїзд", "проїзді"),
    "узвіз": ("узвіз", "узвіз", "узвозі"), "майдан": ("майдан", "майдан", "майдані"), "шосе": ("шосе", "шосе", "шосе"),
    "тупик": ("тупик", "тупик", "тупику"), "в’їзд": ("в’їзд", "в’їзд", "в’їзді"), "м-р": ("м-р", "мікрорайон", "мікрорайоні"),
    "кв-л": ("кв-л", "квартал", "кварталі"),
}
# directory settlement type -> (short forms, full word)
SETTLEMENT_WORDS = {"м.": (("м.",), "місто"), "с.": (("с.",), "село"), "с-ще": (("смт", "с-ще"), "селище")}

# Settlement kind when the text names no settlement of the document's region. Open addresses in court decisions are
# 58 % region centres, 29 % other cities, 2 % towns, 11 % villages (institutions); homes are more rural than that.
KINDS, KIND_WEIGHTS = ("centre", "city", "town", "village"), (0.45, 0.25, 0.07, 0.23)
P_DOC_REGION = 0.85   # an address lies in the region the decision is about
P_DOC_PLACE = 0.8     # … and in a settlement the decision names, when it names one
# which part comes first; one per document. Addresses of hand-labelled decisions: 44 % start with the street, 39 % with the settlement,
# 10 % with the index or the region.
ORDERS, ORDER_WEIGHTS = ("street", "settlement", "region"), (0.45, 0.42, 0.13)
P_ABBR = 0.6          # «вул., буд., кв., м.» against full words; one per document
P_HOUSE_WORD = 0.65   # «буд. 5» against a bare «5»; one per document
P_PO = 0.25           # «по вулиці Центральній»; one per document
# the region and district words are mostly written in full even next to «вул.» and «буд.» («м. Чернівці, Чернівецька
# область»): decided apart from the other abbreviations, one per document
P_REGION_FULL = 0.85
P_DISTRICT_FULL = 0.7
P_PREMISES = 0.05     # «приміщення 213» / «офіс 4» instead of an apartment, for property in a city
P_ZIP = 0.35
P_APT = {"centre": 0.65, "city": 0.6, "town": 0.25, "village": 0.03}
P_REGION = {"centre": 0.45, "city": 0.8, "town": 0.9, "village": 0.9}
P_DISTRICT = {"centre": 0.0, "city": 0.25, "town": 0.85, "village": 0.9}
P_NO_STREET = 0.2     # «с. Іванівка, Броварський район, Київська область» for towns and villages
P_CORP = 0.03
P_OSM = 0.3            # share of OpenStreetMap rows where a settlement is in both tables; Ukrposhta spellings are the usual ones
P_CITY_DISTRICT = 0.15  # «Шевченківський район» of a city, which only OpenStreetMap rows know


def _norm(name: str) -> str:
    return name.lower().replace("’", "'").replace("ʼ", "'")


@lru_cache(maxsize=200_000)
def _forms(word: str) -> tuple[str, ...]:
    """The word as written plus its dictionary forms: «Києві» -> «київ»."""
    return tuple(dict.fromkeys([_norm(word)] + [_norm(p.normal_form) for p in _morph.parse(word)[:6]]))


def _street_locative(name: str) -> str:
    """«по вулиці Центральній» — inflect adjectival street names; genitive-of-person names stay («по вулиці Пушкіна»)."""
    out = []
    for w in name.split():
        parses = [p for p in _morph.parse(w) if "ADJF" in p.tag and "nomn" in p.tag and "femn" in p.tag]
        f = parses[0].inflect({"loct"}) if parses else None
        out.append((f.word[:1].upper() + f.word[1:]) if f else w)
    return " ".join(out)


def default_sources() -> tuple[str, ...]:
    """Ukrposhta first when it was built on this machine, then the bundled OpenStreetMap table."""
    return ("ukrposhta", "osm") if ukrposhta_available() else ("osm",)


@lru_cache(maxsize=4)
def _directory(sources: tuple[str, ...]) -> tuple:
    """Rows of every table and the indexes the generator draws from. The first table that knows a settlement fixes
    its spelling, type and districts; a later table that has the same settlement (region, name and district) adds its
    rows to it."""
    rows: list[tuple] = []
    streets: dict[tuple, dict[str, list[int]]] = {}  # settlement -> table -> its rows
    by_name: dict[tuple, list[tuple]] = {}
    index: dict[tuple, str] = {}  # (settlement, street type, street) -> postal index, for rows that have none
    origin: dict[tuple, str] = {}  # settlement -> the table that named it first
    for src in sources:
        for region, old, new, np_type, np, zip_code, st_type, street, houses, city_district in address_rows(src):
            if np_type not in SETTLEMENT_WORDS or st_type not in STREET_TYPES or not houses:
                continue
            same = sorted(k for k in by_name.get((region, _norm(np)), ()) if origin[k] != src and _norm(k[1]) == _norm(new))
            if same:  # a table read earlier knows the settlement: keep its spelling, type and districts
                key = same[0]
                old = rows[streets[key][origin[key]][0]][1]
            else:
                key = (region, new, np_type, np)
                if key not in origin:
                    origin[key] = src
                    by_name.setdefault((region, _norm(np)), []).append(key)
            street_key = (*key, st_type, _norm(street))
            zip_code = zip_code or index.get(street_key, "")
            if zip_code:
                index.setdefault(street_key, zip_code)
            rows.append((region, old, key[1], key[2], key[3], zip_code, st_type, street, houses, city_district))
            streets.setdefault(key, {}).setdefault(src, []).append(len(rows) - 1)
    if not rows:
        raise ValueError(f"no usable address rows in {sources}")
    # a row with no index of its own takes the most common index of its settlement, when the settlement has one
    zips: dict[tuple, Counter] = {}
    for key, tables in streets.items():
        zips[key] = Counter(rows[i][5] for ids in tables.values() for i in ids if rows[i][5])
    for key, tables in streets.items():
        if zips[key]:
            common = zips[key].most_common(1)[0][0]
            for ids in tables.values():
                for i in ids:
                    if not rows[i][5]:
                        rows[i] = (*rows[i][:5], common, *rows[i][6:])
    kind, by_kind = {}, {}
    for key, tables in streets.items():
        region, _new, np_type, np = key
        k = "centre" if np_type == "м." and np == CENTRES.get(region, (None,))[0] else {"м.": "city", "с-ще": "town", "с.": "village"}[np_type]
        kind[key] = k
        keys, weights = by_kind.setdefault(region, {}).setdefault(k, ([], []))
        keys.append(key)
        # more streets = a bigger settlement; the root keeps small ones visible
        weights.append(len(tables[origin[key]]) ** 0.5)
    by_kind = {r: {k: (keys, list(accumulate(w))) for k, (keys, w) in kinds.items()} for r, kinds in by_kind.items()}
    return rows, streets, kind, by_kind, by_name


class AddressGenerator:
    """`sources`: the address tables to read, in order of preference: «ukrposhta», «osm» or paths to TSV files with
    the columns of uk_legal_faker._data.ADDRESS_COLUMNS. By default every table that is available."""

    def __init__(self, rng: random.Random, sources: tuple[str, ...] | list[str] | None = None):
        self.rng = rng
        self.sources = tuple(sources) if sources else default_sources()
        self.rows, self.streets, self.kind, self.by_kind, self.by_name = _directory(self.sources)
        self.regions = sorted(self.by_kind)

    def _lookup(self, region: str, name: str) -> list[tuple]:
        """Settlements of the region that the name (in any grammatical case) refers to."""
        words = name.split()
        for cand in (words, words[:1]):
            for combo in product(*(_forms(w) for w in cand)):
                found = self.by_name.get((region, " ".join(combo)))
                if found:
                    return found
        return []

    def doc_context(self, text: str = "", region: str | None = None) -> dict:
        """Region and settlements the text names, and one address style for the whole document. `region` (as in
        REGIONS, or «Київ» for the city) overrides the region read from the text."""
        r = self.rng
        if region is not None and region not in self.by_kind:
            raise ValueError(f"unknown region {region!r}: expected one of {sorted(self.by_kind)}")
        region = region or doc_region(text)
        region = region if region in self.by_kind else r.choice(self.regions)
        places, weights = [], []
        for name, n in doc_places(text).items():
            for key in self._lookup(region, name):
                places.append(key)
                weights.append(n)
        return {"region": region, "places": places, "weights": weights, "order": r.choices(ORDERS, ORDER_WEIGHTS)[0],
                "abbr": r.random() < P_ABBR, "house_word": r.random() < P_HOUSE_WORD, "po": r.random() < P_PO,
                "region_full": r.random() < P_REGION_FULL, "district_full": r.random() < P_DISTRICT_FULL}

    def settlement_phrase(self, ctx: dict) -> str:
        """A settlement for «уродженця ІНФОРМАЦІЯ_2» / «місце народження»: «м. Полтава», «с. Іванівка Полтавської області»."""
        r = self.rng
        region = ctx["region"] if r.random() < P_DOC_REGION else r.choice(self.regions)
        _, _, np_type, np = self._settlement(region)
        out = f"{r.choice(SETTLEMENT_WORDS[np_type][0])} {np}"  # abbreviated: the name stays in the nominative
        if region != KYIV and (np_type != "м." or r.random() < 0.3):
            out += f" {inflect_phrase(region + ' область', 'gent')}"
        return out

    def _settlement(self, region: str) -> tuple:
        r = self.rng
        kinds = self.by_kind[region]
        k = r.choices(KINDS, KIND_WEIGHTS)[0]
        if k not in kinds:  # Київська область has no centre of its own, the city of Kyiv has only one settlement
            k = "city" if "city" in kinds else next(iter(kinds))
        keys, cum = kinds[k]
        return r.choices(keys, cum_weights=cum)[0]

    def new_address(self, ctx: dict) -> dict:
        """The parts of one address and how to write it; `render` turns it into text."""
        r = self.rng
        region = ctx["region"] if r.random() < P_DOC_REGION else r.choice(self.regions)
        from_doc = region == ctx["region"] and bool(ctx["places"]) and r.random() < P_DOC_PLACE
        key = r.choices(ctx["places"], ctx["weights"])[0] if from_doc else self._settlement(region)
        tables = self.streets[key]
        first, *others = sorted(tables, key=self.sources.index)
        # where several tables know the settlement, a later one gives the row with probability P_OSM
        src = r.choice(others) if others and r.random() < P_OSM else first
        _, old, new, np_type, np, zip_code, st_type, street, houses, city_district = self.rows[r.choice(tables[src])]
        k = self.kind[key]
        house = r.choice(houses.split(","))
        if r.random() < 0.25:
            house = house.lower()
        district = None
        in_city_district = bool(city_district) and r.random() < P_CITY_DISTRICT
        if in_city_district:
            district = city_district
        elif region != KYIV and r.random() < P_DISTRICT[k]:
            # the directory keeps the district before and after the 2020 reform; a city's «old district» is the city itself
            district = old if k != "city" and old.endswith("ий") and r.random() < 0.5 else new
        no_street = k in ("town", "village") and r.random() < P_NO_STREET
        apt = str(min(int(r.expovariate(1 / 45)) + 1, 400)) if r.random() < P_APT[k] else None
        premises = None
        if apt is None and k in ("centre", "city") and r.random() < P_PREMISES:
            premises = (r.choice(["приміщення", "прим."]), str(r.randint(1, 400))) if r.random() < 0.6 else ("офіс", str(r.randint(1, 60)))
        return {
            "kind": k, "from_doc": from_doc, "src": src, "city_district": in_city_district, "region": region, "district": district,
            "np_type": np_type, "np": np,
            "np_short": r.choice(SETTLEMENT_WORDS[np_type][0]), "zip": zip_code, "st_type": st_type, "street": street, "house": house,
            "apt": apt, "premises": premises,
            "corp": str(r.randint(1, 6)) if k in ("centre", "city") and r.random() < P_CORP else None,
            "with_zip": bool(zip_code) and r.random() < P_ZIP, "with_region": region != KYIV and (no_street or r.random() < P_REGION[k]),
            "no_street": no_street,
            "style": {s: ctx.get(s, True) for s in ("order", "abbr", "house_word", "po", "region_full", "district_full")},
        }

    def render(self, a: dict, variant: bool = False) -> str:
        """The address as text. `variant`: a later mention of the same address, which may switch between abbreviated
        and full words («вул.» / «вулиця»)."""
        st = a["style"]
        abbr = st["abbr"] != variant  # a repeated mention may switch between «вул.» and «вулиця»
        short, full, loc = STREET_TYPES[a["st_type"]]
        settlement = f"{a['np_short']} {a['np']}" if abbr else f"{SETTLEMENT_WORDS[a['np_type']][1]} {a['np']}"
        wider = [f"{a['district']} {'район' if st['district_full'] or not abbr else 'р-н'}"] if a["district"] else []
        if a["with_region"]:
            wider.append(f"{a['region']} {'область' if st['region_full'] or not abbr else 'обл.'}")
        if a["no_street"]:
            return ", ".join(wider[::-1] + [settlement] if st["order"] == "region" else [settlement] + wider)
        if st["po"] and st["order"] == "street" and a["st_type"] == "вул.":
            street = f"по вул. {a['street']}" if abbr else f"по {loc} {_street_locative(a['street'])}"
        else:
            street = f"{short if abbr else full} {a['street']}"
        house = f"{'буд.' if abbr else 'будинок'} {a['house']}" if st["house_word"] else a["house"]
        local = [street, house]
        if a["corp"]:
            local.append(f"{'корп.' if abbr else 'корпус'} {a['corp']}")
        if a["apt"]:
            local.append(f"{'кв.' if abbr else 'квартира'} {a['apt']}")
        elif a.get("premises"):
            local.append(" ".join(a["premises"]))
        index = [a["zip"]] if a["with_zip"] else []
        if st["order"] == "street":      # вулиця, будинок, населений пункт, район, область, індекс
            parts = local + [settlement] + wider + index
        elif st["order"] == "region":    # індекс, область, район, населений пункт, вулиця, будинок
            parts = index + wider[::-1] + [settlement] + local
        else:                            # населений пункт, вулиця, будинок, район, область, індекс
            parts = [settlement] + local + wider + index
        return ", ".join(parts)
