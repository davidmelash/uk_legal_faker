"""Filling the placeholders of a pseudonymized court decision with synthetic values.

The register of court decisions (ЄДРСР) publishes decisions with personal data replaced by placeholders: ОСОБА_1 (a
person), АДРЕСА_1 (an address), НОМЕР_1 (an identifier: tax number, passport, IBAN, phone, plate, …) and
ІНФОРМАЦІЯ_1 (anything else: a date of birth or death, an e-mail, a web address, the name of a military unit or
body, …). The Filler reads the words around each placeholder, chooses a value of the right kind and form, writes it
in the grammatical case the context asks for, and records where it put it.

One placeholder is one identity: every mention of ОСОБА_1 is the same person (declined as each mention needs), every
mention of АДРЕСА_2 the same address. Values agree with each other and with the text: addresses lie in the region the
decision is about, a date «до досягнення дитиною повноліття, тобто до …» is the child's generated birth date plus 18
years, a body that the decision names in the open is not drawn for a placeholder.
"""
from __future__ import annotations

import random
import re
from collections import Counter

from uk_legal_faker.addresses import AddressGenerator
from uk_legal_faker.context import (
    INFO_LEFT,
    INFO_RIGHT,
    guess_gender,
    guess_gender_right,
    guess_org_case,
    guess_person_case,
    info_subtype,
    info_subtypes,
    inside_quotes,
    number_subtype,
)
from uk_legal_faker.document import Entity, FilledDocument, find_placeholders, normalize
from uk_legal_faker.info import DERIVED_CHILD_AGE, KNOWN_SUBTYPES, REF_YEAR, DocState, InfoGenerator
from uk_legal_faker.numbers import NumberGenerator
from uk_legal_faker.orgs import ORG_KINDS, Org, Seen, inner_name
from uk_legal_faker.persons import Person, PersonGenerator

# names in the quotes of the text that are labelled; a surname or a name of unknown kind is masked
QUOTE_KINDS = ("company", "bank", "formation", "institution", "person", "unknown")
# … and only the name of a military formation: a company, a bank, a hospital or a school is not personal data
LABELLED_QUOTES = {"formation"}
CIVIL_QUOTES = {"company", "bank", "institution"}
# sub-types whose value is never a label, whatever the hints say: the rule that finds them is unreliable or the kind
# of the hidden value is not known
ALWAYS_MASKED = {"date_event", "ident", "nick", "place", "other"}
MASK_REASON = "info_unsure"  # a generated value of uncertain kind: it makes the text read naturally, a model should ignore it
# ІНФОРМАЦІЯ covers «назва військової частини»; the name of a civil body or a company identifies no natural person.
# Clerks hide such names now and then, and the same names stand open in most decisions, so the value is neither
# personal data nor plain text: a mask.
CIVIL_REASON = "info_civil_org"
_MILITARY = re.compile(r"(військов|оборони|ТЦК|комплектування|мобілізац|грошового забезпечення)", re.I)
_COMMERCIAL = re.compile(r"(господарськ\w+\s+суд|\bГПК\b)", re.I)
_SOCIAL = re.compile(r"(пенсі[йяюї]|соціальн\w+\s+(?:захист|допомог|виплат)|державн\w+\s+допомог|інвалідн)", re.I)
# «(далі - », «(далі також - відповідач, »: the slot of a short name; the body it abbreviates stands right before the bracket
_SHORT_SLOT = re.compile(r"\(\s*дал[іi]\s*(?:також\s*)?[-–—]?\s*(?:[^()]{0,40}[,;]\s*)?$", re.I)
_PERSON_REF = re.compile(r"ОСОБА_(\d+)")
# «до досягнення ОСОБА_3, ІНФОРМАЦІЯ_2, повноліття, тобто до », «до закінчення ОСОБА_2, ІНФОРМАЦІЯ_4, навчання … (тобто »:
# the birth date named inside the clause of a derived date is the one it is computed from
_DERIVED_CLAUSE_DOB = re.compile(r"(?:досягнення|закінчення|повноліття)[^.;]{0,60}?ОСОБА_\d+\s*,?\s*\(?\s*ІНФОРМАЦІЯ_(\d+)[^.;]{0,90}$", re.I)
# «до досягнення ОСОБА_3 повноліття, тобто до », «до повноліття сина ОСОБА_4, тобто до »: the child, named without a date
_DERIVED_CLAUSE_PERSON = re.compile(r"(?:досягнення|повноліття|закінчення\s+навчання)\s+(?:[а-яіїє]+\s+){0,2}?ОСОБА_(\d+)[^.;]{0,60}$", re.I)
DERIVED_LOOK_BACK = 200  # characters before a derived date in which the child's birth date is looked for
TAIL = 200               # characters of the filled text kept for the values that depend on it


def resolve_subtype(st: str, hints: dict) -> tuple[str, dict]:
    """The sub-type and hints the generators work with: a sub-type they do not know becomes a masked «other», a name
    in quotes or an institution of an unknown kind becomes the masked kind, and `mask` is set wherever the value
    must not be a label."""
    hints = dict(hints or {})
    if st not in KNOWN_SUBTYPES:
        return "other", {"mask": True}
    if st == "quoted":
        kind = hints.get("quote_kind", "company")  # the rules always name the kind; a bare «quoted» is a company
        hints["quote_kind"] = kind if kind in QUOTE_KINDS else "unknown"
        if hints["quote_kind"] not in LABELLED_QUOTES:
            hints["mask"] = True
            if hints["quote_kind"] in CIVIL_QUOTES:
                hints["reason"] = CIVIL_REASON
    if st == "org":
        kind = hints.get("org_kind", "party")
        hints["org_kind"] = kind if kind in ORG_KINDS else "party"
        if hints["org_kind"] == "official":
            hints["mask"] = True
    if st in ALWAYS_MASKED:
        hints["mask"] = True
    hints["mask"] = hints.get("mask") is True
    return st, hints


def link_derived(text: str, phs: list[dict], info_sub: dict[int, tuple[str, dict]]) -> tuple[dict[int, int], dict[int, tuple[int, int]]]:
    """Which birth date every derived date («до досягнення повноліття, тобто до …») is computed from, read from the text
    before it is filled: the birth date named in the clause of the derived date («до досягнення ОСОБА_3, ІНФОРМАЦІЯ_2,
    повноліття»), or the one that follows another mention of the person named there; else the nearest birth date of a
    child in the 200 characters before it; else the child's birth date that follows another mention of the person
    named last before it. Outside the clause a birth date counts as a child's by its own mention, not by the vote
    over all mentions of the placeholder.
    Returns derived index -> birth-date index, and birth-date index -> (lowest, highest) age of the person: a derived
    date in the future needs a child of that age."""
    derived = {idx: hints.get("until", "majority") for idx, (st, hints) in info_sub.items() if st == "derived"}
    dob = {idx for idx, (st, _) in info_sub.items() if st == "dob"}
    if not derived or not dob:
        return {}, {}
    # birth-date placeholders whose own context has a child cue: (position, index), and the person named right before
    child_at: list[tuple[int, int]] = []
    of_person: dict[int, int] = {}   # person index -> the birth date of a child that follows a mention of the person
    of_anybody: dict[int, int] = {}  # … -> the birth date that follows a mention of the person, child or not
    for p in phs:
        if p["type"] == "ІНФОРМАЦІЯ" and p["idx"] in dob:
            left = text[max(0, p["start"] - INFO_LEFT): p["start"]]
            st, hints = info_subtype(left, text[p["end"]: p["end"] + INFO_RIGHT])
            person = re.search(r"ОСОБА_(\d+)\s*,?\s*\(?\s*$", left)
            if person and st == "dob":
                of_anybody.setdefault(int(person.group(1)), p["idx"])
            if st == "dob" and hints.get("child"):
                child_at.append((p["start"], p["idx"]))
                if person:
                    of_person.setdefault(int(person.group(1)), p["idx"])
    source: dict[int, int] = {}
    ages: dict[int, tuple[int, int]] = {}
    for p in phs:
        idx = p["idx"]
        if p["type"] != "ІНФОРМАЦІЯ" or idx not in derived or idx in source:
            continue
        left = text[max(0, p["start"] - DERIVED_LOOK_BACK): p["start"]]
        clause, named = _DERIVED_CLAUSE_DOB.search(left), _DERIVED_CLAUSE_PERSON.search(left)
        near = [i for pos, i in child_at if p["start"] - DERIVED_LOOK_BACK <= pos < p["start"]]
        persons = _PERSON_REF.findall(left)
        if clause and int(clause.group(1)) in dob:
            src = int(clause.group(1))
        elif named and int(named.group(1)) in of_anybody:
            src = of_anybody[int(named.group(1))]
        else:
            src = near[-1] if near else of_person.get(int(persons[-1])) if persons else None
        # two children of one decision do not come of age on one day: a birth date gives one derived date of a kind
        if src is None or any(source[d] == src and derived[d] == derived[idx] for d in source):
            continue
        source[idx] = src
        low, high = DERIVED_CHILD_AGE.get(derived[idx], DERIVED_CHILD_AGE["majority"])
        ages[src] = (max(low, ages[src][0]), min(high, ages[src][1])) if src in ages else (low, high)
    # «до повноліття» and «до трьох років» of one child can leave no age: the narrower demand wins
    return source, {i: (min(a), min(a)) if a[0] > a[1] else a for i, a in ages.items()}


def person_genders(text: str, phs: list[dict]) -> dict[int, str]:
    """The gender of every ОСОБА placeholder: a vote over the words before each mention («позивачка ОСОБА_1») and the
    verb after it («ОСОБА_1 звернувся»); a tie goes to the first cue in the text. No cue: not in the result."""
    votes: dict[int, list[str]] = {}
    for p in phs:
        if p["type"] == "ОСОБА":
            for g in (guess_gender(text[max(0, p["start"] - 90): p["start"]]), guess_gender_right(text[p["end"]: p["end"] + 80])):
                if g:
                    votes.setdefault(p["idx"], []).append(g)
    return {idx: max(dict.fromkeys(v), key=v.count) for idx, v in votes.items()}


class Filler:
    """Fills pseudonymized decisions.

    `seed`: makes the output reproducible (None: a random one). `ref_year`: the year the decisions are from; ages and
    recent dates count from it. `address_sources`: address tables, see AddressGenerator. `org_names`: real
    organisation names, see OrgGenerator.
    """

    def __init__(self, seed: int | str | None = None, ref_year: int = REF_YEAR, address_sources=None, org_names: dict | None = None,
                 rng: random.Random | None = None):
        """`rng`: a random generator to share (e.g. Faker's); `seed` then only names the per-document streams of
        fill(doc_id=…), and nothing is drawn from `rng` here."""
        if seed is None and rng is None:
            seed = random.randrange(2**32)
        self.seed = seed
        self.rng = rng or random.Random(seed)
        self.persons = PersonGenerator(self.rng)
        self.addresses = AddressGenerator(self.rng, address_sources)
        self.numbers = NumberGenerator(self.rng)
        self.info = InfoGenerator(self.rng, self.persons, ref_year=ref_year, org_names=org_names)
        self.stats: Counter = Counter()  # what was generated: cases, address kinds, sub-types, masks (diagnostics)

    def fill(self, text: str, doc_id: str | None = None, kind: str | None = None, version: int = 1,
             normalize_text: bool = True) -> FilledDocument:
        """Replace every placeholder of `text` with a synthetic value.

        `doc_id`: with it, the values depend only on the seed, the id and `version` - not on the documents filled
        before - so a corpus can be refilled document by document. `version` numbers other fillings of the same
        document (other values in the same places). `kind`: the kind of decision, «ГПК» for a commercial case (it
        shifts institutions towards companies). `normalize_text`: tidy the register's spacing around placeholders
        first («ОСОБА_1 ,» -> «ОСОБА_1,»); FilledDocument.source is the text after this step.
        """
        if doc_id is not None:
            # every document has its own random stream: a change in one fill, or in the set of documents, leaves the
            # other texts as they were
            self.rng.seed(f"{self.seed}:{doc_id}" + (f":{version}" if version > 1 else ""))
        if normalize_text:
            text = normalize(text)
        phs = find_placeholders(text)
        # per-document registries: one identity per placeholder index
        people: dict[int, Person] = {}
        addrs: dict[int, dict] = {}
        nums: dict[int, str] = {}
        infos: dict[int, tuple[str, str | Org, dict]] = {}
        seen_person: set[int] = set()

        # decide НОМЕР / ІНФОРМАЦІЯ sub-types from the most informative occurrence
        num_sub: dict[int, str] = {}
        for p in phs:
            if p["type"] == "НОМЕР":
                st = number_subtype(text[max(0, p["start"] - 60): p["start"]], text[p["end"]: p["end"] + 40])
                if st != "generic" or p["idx"] not in num_sub:
                    num_sub[p["idx"]] = st
        info_sub = {idx: resolve_subtype(st, hints) for idx, (st, hints) in info_subtypes(text, phs).items()}
        genders = person_genders(text, phs)
        # the names the decision has in the open and the birth date of a child, for the values that depend on them
        state = DocState(Seen(text))
        state.derived_from, state.child_age = link_derived(text, phs, info_sub)
        # what the decision is about decides which institutions it anonymises
        org_ctx = {"military": bool(_MILITARY.search(text)),
                   "commercial": kind == "ГПК" or bool(_COMMERCIAL.search(text[:3000])),
                   "social": bool(_SOCIAL.search(text))}

        # one address area / style and one date format per document
        addr_ctx = None
        date_style = self.info.doc_date_style()
        # a person to tie e-mails / nicknames to: the one mentioned most recently before the placeholder
        out: list[str] = []
        entities: list[Entity] = []
        pos = length = 0  # position in the source text, length of the filled text so far
        last_person = None
        tail = ""  # the end of the filled text so far
        for p in phs:
            out.append(text[pos: p["start"]])
            tail = (tail + out[-1])[-TAIL:]
            start = length + len(out[-1])
            t, idx = p["type"], p["idx"]
            left = text[max(0, p["start"] - 90): p["start"]]
            right = text[p["end"]: p["end"] + INFO_RIGHT]
            mask_reason = None
            if t == "ОСОБА":
                if idx not in people:
                    people[idx] = self.persons.new_person(genders.get(idx))
                person = people[idx]
                case = self.persons.choose_case(guess_person_case(left))
                value = self.persons.render(person, case, first_mention=idx not in seen_person)
                seen_person.add(idx)
                last_person = person
                self.stats[f"case_{case}"] += 1
            elif t == "АДРЕСА":
                if idx not in addrs:
                    addr_ctx = addr_ctx or self.addresses.doc_context(text)
                    a = addrs[idx] = self.addresses.new_address(addr_ctx)
                    self.stats.update([f"addr_kind_{a['kind']}", f"addr_order_{a['style']['order']}", f"addr_src_{a['src']}"]
                                      + [f"addr_{k}" for k in ("from_doc", "with_zip", "apt", "no_street", "city_district") if a[k]])
                    value = self.addresses.render(a)
                else:
                    value = self.addresses.render(addrs[idx], variant=self.rng.random() < 0.3)
            elif t == "НОМЕР":
                if idx not in nums:
                    nums[idx] = self.numbers.generate(num_sub.get(idx, "generic"), text[max(0, p["start"] - 20): p["start"]])
                    self.stats[f"num_{num_sub.get(idx, 'generic')}"] += 1
                value = nums[idx]
            else:  # ІНФОРМАЦІЯ
                st, hints = info_sub.get(idx, ("other", {"mask": True}))
                if idx not in infos:
                    if st == "place":  # «уродженця ІНФОРМАЦІЯ_2»: a settlement, in the area of the decision
                        addr_ctx = addr_ctx or self.addresses.doc_context(text)
                        v = self.addresses.settlement_phrase(addr_ctx)
                    elif st == "org" and not hints["mask"] and hints["org_kind"] in ("short", "party") and _SHORT_SLOT.search(left):
                        # «військової частини А5885 (далі - 【X】)»: the short name of the body before the bracket, which
                        # may itself be a value filled a moment ago; a body with no usual short name gets a random one,
                        # masked when the slot is of the «short» kind (it would contradict the name next to it)
                        v = self.info.org_gen.short_for(tail[: tail.rfind("(")])
                        if v is not None:
                            state.seen.add(v)
                            self.stats["info_short_from_antecedent"] += 1
                        else:
                            if hints["org_kind"] == "short":
                                st, hints = info_sub[idx] = (st, {**hints, "mask": True})
                            v = self.info.generate(st, hints, last_person, date_style, org_ctx, state, left, right, idx)
                    else:
                        v = self.info.generate(st, hints, last_person, date_style, org_ctx, state, left, right, idx)
                    if st == "org" and not hints["mask"] and self.info.org_gen.last_kind in ("civil", "company"):
                        # the body that was drawn is not a military one: every mention of it is masked
                        st, hints = info_sub[idx] = (st, {**hints, "mask": True, "reason": CIVIL_REASON})
                        self.stats[f"info_civil_{self.info.org_gen.last_kind}"] += 1
                    infos[idx] = (st, v, hints)
                    self.stats[f"info_{st}"] += 1
                    if hints["mask"]:
                        self.stats[f"info_civil_masked_{st}" if hints.get("reason") == CIVIL_REASON else f"info_masked_{st}"] += 1
                    if st == "org":
                        self.stats[f"info_orgkind_{hints['org_kind']}"] += 1
                    if st == "quoted":
                        self.stats[f"info_quotekind_{hints['quote_kind']}"] += 1
                    if isinstance(v, Org):
                        self.stats[f"info_org_{'military' if org_ctx['military'] else 'commercial' if org_ctx['commercial'] else 'other'}"] += 1
                    if st in ("dob", "death", "derived", "date_event"):
                        self.stats[f"date_doc_style_{date_style}"] += 1
                v = infos[idx][1]
                if hints["mask"]:  # every mention of the placeholder: the value is one per index, and so is its doubt
                    mask_reason = hints.get("reason", MASK_REASON)
                # an institution is declined by the case its context asks for, like a person's name
                value = v.render(guess_org_case(left)) if isinstance(v, Org) else v
                if isinstance(v, Org) and inside_quotes(left, right):
                    # «з КНЗ ЦТЗ «【X】»»: the text has the quotes, so only the name that a body carries in its own
                    value = inner_name(v.render())
            out.append(value)
            tail = (tail + value)[-TAIL:]
            subtype = None if t in ("ОСОБА", "АДРЕСА") else num_sub.get(idx, "generic") if t == "НОМЕР" else infos[idx][0]
            entities.append(Entity(start, start + len(value), t, f"{t}_{idx}", value, subtype, mask_reason))
            length = start + len(value)
            pos = p["end"]
        out.append(text[pos:])
        return FilledDocument("".join(out), text, entities, doc_id, {"kind": kind, "version": version, "n_persons": len(people)})
