"""Synthetic persons: Ukrainian surname, first name and patronymic, declined by grammatical case.

Names are drawn from frequency lists of Ukrainian names (lang-uk/name_freq_dict_uk, flattened by the square root of
the frequency so that a few public figures do not dominate). A feminine surname is derived from the masculine one
(«Ковальський» -> «Ковальська»).
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

from uk_legal_faker._data import name_pools
from uk_legal_faker.morph import CASES, inflect_full

_FEM_SURNAME = [
    ("ський", "ська"), ("цький", "цька"), ("зький", "зька"), ("ий", "а"), ("ій", "я"),
    ("ов", "ова"), ("ев", "ева"), ("єв", "єва"), ("ін", "іна"), ("ин", "ина"), ("їн", "їна"),
]
# court texts prefer the short dative: «Шевченку», «Ковалю», «Івановичу», «Іллічу» (the dictionary gives «Шевченкові»,
# «Ковалеві», «Івановичеві», «Іллічеві»): -еві after a hushing consonant becomes -у, after any other -ю
_DATV_COURT = [(re.compile(r"(?<=[жчшщ])еві$"), "у"), (re.compile(r"ові$"), "у"), (re.compile(r"[еє]ві$"), "ю")]


def short_dative(word: str) -> str:
    """«Шевченкові» -> «Шевченку», «Ковалеві» -> «Ковалю», «Івановичеві» -> «Івановичу»; other words stay."""
    for rx, short in _DATV_COURT:
        if rx.search(word):
            return rx.sub(short, word)
    return word
# how often each case stands where the context does not tell (counted on court decisions)
CASE_PRIOR = (("nomn", 45), ("gent", 40), ("datv", 7), ("accs", 5), ("ablt", 3))
GENDERS = ("masc", "femn")
# surface forms of a mention: «Шевченко Тарас Григорович», «Шевченко Т.Г.», «Т. Г. Шевченко», …
FORMS = ("full", "initials", "first_initial", "first_last", "initials_first")


@dataclass(frozen=True)
class Person:
    """A synthetic person. `gender` is «masc» or «femn»; the names are in the nominative."""
    gender: str
    surname: str
    first: str
    patr: str

    def initials(self, space: bool = False) -> str:
        sep = " " if space else ""
        return f"{self.first[0]}.{sep}{self.patr[0]}."

    def name(self, case: str = "nomn", form: str = "full", space: bool = False) -> str:
        """The name in a grammatical case (one of CASES) and a surface form (one of FORMS); `space` puts a space
        between the initials («Т. Г.»). A masculine dative takes the short ending of court texts («Шевченку»)."""
        if case not in CASES:
            raise ValueError(f"unknown case {case!r}: expected one of {CASES}")
        s, f, pa = inflect_full(self.surname, self.first, self.patr, self.gender, case)
        if case == "datv" and self.gender == "masc":
            s, f, pa = short_dative(s), short_dative(f), short_dative(pa)
        if form == "full":
            return f"{s} {f} {pa}"
        if form == "initials":
            return f"{s} {self.initials(space)}"
        if form == "first_initial":
            return f"{s} {self.first[0]}."
        if form == "first_last":
            return f"{f} {s}"
        if form == "initials_first":
            return f"{self.initials(space)} {s}"
        raise ValueError(f"unknown form {form!r}: expected one of {FORMS}")

    def __str__(self) -> str:
        return self.name()


class PersonGenerator:
    """Draws persons and renders their mentions the way court decisions write them."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.pools = {k: ([n for n, _ in v], [w for _, w in v]) for k, v in name_pools().items()}

    def _pick(self, key: str) -> str:
        names, weights = self.pools[key]
        return self.rng.choices(names, weights)[0]

    def new_person(self, gender: str | None = None) -> Person:
        """A person of `gender` («masc» / «femn»); a random one (52 % men) when it is None."""
        if gender is not None and gender not in GENDERS:
            raise ValueError(f"unknown gender {gender!r}: expected one of {GENDERS}")
        gender = gender or ("masc" if self.rng.random() < 0.52 else "femn")
        surname = self._pick("surname")
        if gender == "femn":
            for m, f in _FEM_SURNAME:
                if surname.endswith(m):
                    surname = surname[: -len(m)] + f
                    break
        first = self._pick("male_first" if gender == "masc" else "female_first")
        patr = self._pick("male_patr" if gender == "masc" else "female_patr")
        return Person(gender, surname, first, patr)

    def choose_case(self, guessed: str | None) -> str:
        """The case the context asked for, else one drawn from CASE_PRIOR."""
        if guessed:
            return guessed
        return self.rng.choices([c for c, _ in CASE_PRIOR], [w for _, w in CASE_PRIOR])[0]

    def _court_dative(self, parts: tuple[str, str, str]) -> tuple[str, str, str]:
        if self.rng.random() > 0.7:
            return parts
        return tuple(short_dative(w) for w in parts)  # type: ignore[return-value]

    def render(self, p: Person, case: str, first_mention: bool) -> str:
        """One mention of `p` in `case`: the full name on the first mention, later mostly the full name again, sometimes
        the surname with initials («Шевченко Т.Г.», «Т. Г. Шевченко») or the first name and surname. A masculine dative
        takes the short ending of court texts («Шевченку») seven times in ten."""
        r = self.rng.random()
        s, f, pa = inflect_full(p.surname, p.first, p.patr, p.gender, case)
        if case == "datv" and p.gender == "masc":
            s, f, pa = self._court_dative((s, f, pa))
        if first_mention or r < 0.82:
            return f"{s} {f} {pa}"
        if r < 0.92:
            return f"{s} {p.initials(space=self.rng.random() < 0.5)}"
        if r < 0.95:
            return f"{s} {p.first[0]}."
        if r < 0.975:
            return f"{f} {s}"
        return f"{p.initials(space=self.rng.random() < 0.5)} {s}"


def translit(word: str) -> str:
    """Latin spelling for e-mails, logins and profile links (close to the national transliteration, lower case)."""
    table = {
        "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie", "ж": "zh", "з": "z", "и": "y",
        "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
        "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ь": "", "ю": "iu",
        "я": "ia", "'": "", "’": "", "-": "",
    }
    return "".join(table.get(ch, ch) for ch in word.lower())
