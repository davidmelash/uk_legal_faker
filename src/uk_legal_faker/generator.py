"""LegalFaker: the public entry point.

    >>> from uk_legal_faker import LegalFaker
    >>> fake = LegalFaker(seed=1)
    >>> fake.name(case="gent")            # «Коваленка Олега Петровича»
    >>> fake.address(region="Львівська")  # «вул. Шевченка, буд. 12, кв. 4, м. Самбір, Львівська область»
    >>> fake.fill("Позов ОСОБА_1 до ІНФОРМАЦІЯ_1 про стягнення").text
"""
from __future__ import annotations

import datetime as dt
import random
from pathlib import Path

from uk_legal_faker import _data
from uk_legal_faker.document import FilledDocument
from uk_legal_faker.filler import Filler
from uk_legal_faker.info import DATE_STYLES, DATE_WEIGHTS, REF_YEAR
from uk_legal_faker.orgs import MOBILE_OPERATORS, Org
from uk_legal_faker.persons import Person

# what LegalFaker.org() can draw
ORG_KINDS = ("military_unit", "unit_name", "military_body", "tck", "medical_commission", "civil_body", "company", "bank",
             "court", "prosecutors_office", "police", "hospital", "mobile_operator")
# НОМЕР sub-types of the number generator, by the name of the LegalFaker method
_NUMBERS = {"rnokpp": "rnokpp", "passport": "passport", "iban": "iban", "bank_card": "card", "phone": "phone", "imei": "imei",
            "certificate_number": "svidotstvo", "military_unit_code": "military", "vin": "vin", "license_plate": "vehicle",
            "enforcement_proceeding_number": "provadzhennia", "personal_number": "generic"}
URL_KINDS = ("site", "page", "profile")


class LegalFaker:
    """Synthetic personal data of Ukrainian court decisions, and decisions filled with it.

    `seed`: makes every call reproducible (None: random). `ref_year`: the year the documents are from; ages and recent
    dates count from it. `address_sources`: address tables in order of preference («ukrposhta», «osm» or paths to TSV
    files; default: every table available). `org_names`: real organisation names that replace a share of the
    composed civil bodies and companies (a dict or a TSV / CSV file, see docs/data.md).

    Every value is drawn from one random stream; `fill(..., doc_id=…)` reseeds it from the seed and the id.
    """

    def __init__(self, seed: int | str | None = None, *, ref_year: int = REF_YEAR, address_sources=None,
                 org_names: dict | str | Path | None = None, rng: random.Random | None = None):
        names = _data.load_org_names(org_names) if org_names is not None else None
        self._filler = Filler(seed, ref_year=ref_year, address_sources=address_sources, org_names=names, rng=rng)
        self.rng = self._filler.rng
        self._persons = self._filler.persons
        self._addresses = self._filler.addresses
        self._numbers = self._filler.numbers
        self._info = self._filler.info
        self._orgs = self._info.org_gen

    def seed(self, seed: int | str) -> None:
        """Restart the random stream."""
        self._filler.seed = seed
        self.rng.seed(seed)

    @property
    def ref_year(self) -> int:
        return self._info.ref_year

    # --- persons ------------------------------------------------------------------------------------------------
    def person(self, gender: str | None = None) -> Person:
        """A person («masc» / «femn», random when None); `Person.name(case, form)` writes any mention of it."""
        return self._persons.new_person(gender)

    def name(self, case: str = "nomn", gender: str | None = None, form: str = "full") -> str:
        """A full name in a grammatical case: nomn, gent, datv, accs, ablt. `form`: full, initials («Шевченко Т.Г.»),
        first_initial, first_last, initials_first («Т.Г. Шевченко»)."""
        return self.person(gender).name(case, form)

    def surname(self, gender: str | None = None) -> str:
        return self.person(gender).surname

    def first_name(self, gender: str | None = None) -> str:
        return self.person(gender).first

    def patronymic(self, gender: str | None = None) -> str:
        return self.person(gender).patr

    # --- addresses ----------------------------------------------------------------------------------------------
    @property
    def regions(self) -> list[str]:
        """Regions the address tables cover («Київ» is the city)."""
        return list(self._addresses.regions)

    def address(self, region: str | None = None) -> str:
        """A full address of a real street and house («вул. Січових Стрільців, 12, кв. 5, м. Тернопіль, 46000»), in one of
        the word orders and abbreviation styles of court decisions. `region` as in `regions` (random when None)."""
        ctx = self._addresses.doc_context(region=region)
        return self._addresses.render(self._addresses.new_address(ctx))

    def settlement(self, region: str | None = None) -> str:
        """A place of birth: «м. Полтава», «с. Іванівка Полтавської області»."""
        return self._addresses.settlement_phrase(self._addresses.doc_context(region=region))

    # --- numbers ------------------------------------------------------------------------------------------------
    def rnokpp(self) -> str:
        """Taxpayer registration number (РНОКПП / ІПН): 10 digits."""
        return self._numbers.generate("rnokpp")

    def passport(self) -> str:
        """Passport: a booklet («КВ 123456», «серії КВ № 123456») or an ID card («123456789», with УНЗР sometimes)."""
        return self._numbers.generate("passport")

    def iban(self) -> str:
        """Ukrainian IBAN of a personal account (UA + 27 digits), grouped by four now and then."""
        return self._numbers.generate("iban")

    def bank_card(self) -> str:
        return self._numbers.generate("card")

    def phone(self) -> str:
        """Mobile number in one of the ways decisions write it: «+380501234567», «(067) 123-45-67», …"""
        return self._numbers.generate("phone")

    def imei(self) -> str:
        return self._numbers.generate("imei")

    def certificate_number(self) -> str:
        """Series and number of a certificate, diploma or driving licence: «АВ 123456»."""
        return self._numbers.generate("svidotstvo")

    def military_unit_code(self) -> str:
        """Code of a military unit: «А1234»."""
        return self._numbers.generate("military")

    def vin(self) -> str:
        return self._numbers.generate("vin")

    def license_plate(self) -> str:
        """Vehicle plate in Cyrillic or Latin letters: «АА 1234 ВС», «KA1234XB»."""
        return self._numbers.generate("vehicle")

    def enforcement_proceeding_number(self) -> str:
        """Number of an enforcement proceeding (ВП): 8 to 10 digits or «АВ/1234»."""
        return self._numbers.generate("provadzhennia")

    def personal_number(self) -> str:
        """Any of the identifiers above or a serial-like code, as an unspecified НОМЕР."""
        return self._numbers.generate("generic")

    # --- dates --------------------------------------------------------------------------------------------------
    def date_of_birth(self, minor: bool = False) -> dt.date:
        """A minor is 1-17 years old in `ref_year`; an adult mostly 25-50, otherwise 18-80."""
        return self._info._birth(child=minor, adult=not minor)

    def date_of_death(self, born: dt.date | None = None, war: bool = False) -> dt.date:
        """A date of the last 21 years, after `born` when given; with `war`, on or after 24.02.2022."""
        return self._info._death(born, war)

    def format_date(self, date: dt.date, style: str | None = None) -> str:
        """`style`: iso (2001-05-17), numeric (17.05.2001), words (17 травня 2001), words_roku (… 2001 року),
        words_narodzh (… 2001 року народження); random by the shares of court decisions when None."""
        style = style or self.rng.choices(DATE_STYLES, DATE_WEIGHTS)[0]
        if style not in DATE_STYLES:
            raise ValueError(f"unknown date style {style!r}: expected one of {DATE_STYLES}")
        return self._info.render_date(date, style)

    def birth_date(self, minor: bool = False, style: str | None = None) -> str:
        return self.format_date(self.date_of_birth(minor), style)

    # --- internet -----------------------------------------------------------------------------------------------
    def email(self, person: Person | None = None) -> str:
        """A personal e-mail, mostly built from the person's name when one is given."""
        return self._info.generate("email", {}, person or (self.person() if self.rng.random() < 0.7 else None))

    def url(self, kind: str = "page", person: Person | None = None) -> str:
        """`kind`: site (a home page), page (an article, a video or a post), profile (a social-network profile)."""
        if kind not in URL_KINDS:
            raise ValueError(f"unknown url kind {kind!r}: expected one of {URL_KINDS}")
        return self._info.generate("url", {"url_kind": kind}, person or self.person())

    def social_account(self, person: Person | None = None) -> str:
        """A nickname («@kovalenko12») or a channel / page link."""
        kind = "page" if self.rng.random() < 0.5 else "handle"
        return self._info.generate("nick", {"nick_kind": kind}, person or self.person())

    def login(self, person: Person | None = None) -> str:
        """A login or an identifier of an information system."""
        return self._info.generate("ident", {}, person or self.person())

    # --- organisations ------------------------------------------------------------------------------------------
    def org(self, kind: str = "military_body") -> Org:
        """An organisation that renders itself in any case: `org(...).render("gent")`. `kind` is one of ORG_KINDS."""
        o = self._orgs
        draw = {"military_unit": o.unit, "unit_name": o.own_unit_name, "military_body": o.military_body, "tck": o.tck,
                "medical_commission": o.medical, "civil_body": o.civil_body, "company": lambda: o.company(commercial=True),
                "bank": o.bank, "court": lambda: o.official("судді"), "prosecutors_office": o.prosecutors_office,
                "police": o.police_unit, "hospital": o.hospital, "mobile_operator": self._mobile_operator}.get(kind)
        if draw is None:
            raise ValueError(f"unknown organisation kind {kind!r}: expected one of {ORG_KINDS}")
        return draw()

    def _mobile_operator(self) -> Org:
        form, name = self.rng.choice(MOBILE_OPERATORS)
        return Org(form, f"«{name}»", fixed=True)

    def military_unit(self, case: str = "nomn") -> str:
        """«Військова частина А1234», «в/ч А1234», «Окрема механізована бригада «Холодний Яр»», …"""
        return self.org("military_unit").render(case)

    def military_unit_name(self, case: str = "nomn") -> str:
        """The own name of a unit: «72 окрема механізована бригада», «Мукачівський прикордонний загін», …"""
        return self.org("unit_name").render(case)

    def military_body(self, case: str = "nomn") -> str:
        """The ministry, a command, a ТЦК, a unit, a military medical commission or a КЕВ."""
        return self.org("military_body").render(case)

    def tck(self, case: str = "nomn") -> str:
        """A territorial centre of recruitment and social support (ТЦК та СП)."""
        return self.org("tck").render(case)

    def civil_body(self, case: str = "nomn") -> str:
        """A state body (tax service, Pension Fund, police, migration service, …), a council or an administration."""
        return self.org("civil_body").render(case)

    def company(self, case: str = "nomn") -> str:
        """A company with its legal form: «ТОВ «Комтех Логістік»», «Приватне підприємство «Дельта»»."""
        return self.org("company").render(case)

    def company_name(self) -> str:
        """A bare company name, as it stands inside quotes: «Укрбудінвест»."""
        return self._orgs.company_name(commercial=True)

    def bank(self) -> str:
        return self.org("bank").render()

    def court(self, case: str = "nomn") -> str:
        return self.org("court").render(case)

    def prosecutors_office(self, case: str = "nomn") -> str:
        return self.org("prosecutors_office").render(case)

    def police_unit(self, case: str = "nomn") -> str:
        return self.org("police").render(case)

    def hospital(self, case: str = "nomn") -> str:
        return self.org("hospital").render(case)

    # --- documents ----------------------------------------------------------------------------------------------
    def fill(self, text: str, doc_id: str | None = None, kind: str | None = None, version: int = 1,
             normalize_text: bool = True) -> FilledDocument:
        """Replace the placeholders of a pseudonymized decision (ОСОБА_1, АДРЕСА_1, НОМЕР_1, ІНФОРМАЦІЯ_1) with synthetic
        values that fit their context; see Filler.fill for the arguments."""
        return self._filler.fill(text, doc_id=doc_id, kind=kind, version=version, normalize_text=normalize_text)

    @staticmethod
    def templates(kind: str | None = None) -> list[dict]:
        """The bundled pseudonymized decisions (`id`, `kind`, `case`, `source`, `text`); `kind` filters them: ВС
        (Supreme Court), ЦПК (civil), КАС (administrative), військові (servicemen's cases), КПК (criminal), ГПК
        (commercial)."""
        return [dict(d) for d in _data.decisions() if kind is None or d["kind"] == kind]

    def court_decision(self, kind: str | None = None) -> FilledDocument:
        """A real court decision of 2024 with every placeholder filled: text plus entity spans."""
        pool = self.templates(kind)
        if not pool:
            kinds = sorted({d["kind"] for d in _data.decisions()})
            raise ValueError(f"no template of kind {kind!r}: expected one of {kinds}")
        tpl = self.rng.choice(pool)
        doc = self._filler.fill(tpl["text"], kind=tpl["kind"], normalize_text=False)
        doc.id = tpl["id"]
        doc.meta.update(case=tpl.get("case"), source=tpl.get("source"))
        return doc

    @property
    def stats(self):
        """Counters of what `fill` generated (cases, address kinds, sub-types, masks) - for dataset reports."""
        return self._filler.stats
