"""Placeholders of pseudonymized court decisions and the result of filling them."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

# entity types of the Unified State Register of Court Decisions (ЄДРСР)
PERSON, ADDRESS, NUMBER, INFO = "ОСОБА", "АДРЕСА", "НОМЕР", "ІНФОРМАЦІЯ"
ENTITY_TYPES = (PERSON, ADDRESS, NUMBER, INFO)
PLACEHOLDER = re.compile(r"(ОСОБА|АДРЕСА|НОМЕР|ІНФОРМАЦІЯ)_(\d+)")

_SPACE_BEFORE_PUNCT = re.compile(r"[ \t ]+([,.;:)»])")
_SPACE_AFTER_OPEN = re.compile(r"([(«])[ \t ]+")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def normalize(text: str) -> str:
    """Tidy the spacing the register leaves around placeholders: «ОСОБА_1 ,» -> «ОСОБА_1,», «( ОСОБА_2» -> «(ОСОБА_2»;
    unify line breaks and non-breaking spaces."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN.sub(r"\1", text)
    return _MULTI_SPACE.sub(" ", text)


def find_placeholders(text: str) -> list[dict]:
    """Every placeholder of the text: {"start", "end", "type", "idx"}, in text order."""
    return [{"start": m.start(), "end": m.end(), "type": m.group(1), "idx": int(m.group(2))} for m in PLACEHOLDER.finditer(text)]


@dataclass(frozen=True)
class Entity:
    """One generated value in the filled text.

    `start` / `end` are character offsets in FilledDocument.text (`end` exclusive), `label` is the entity type
    (ОСОБА, АДРЕСА, НОМЕР, ІНФОРМАЦІЯ), `placeholder` the placeholder it replaced («ОСОБА_1»: every mention of one
    placeholder is the same identity), `subtype` what kind of value was generated («rnokpp», «dob», «org», …).
    `mask` is None for a value that is personal data in the sense of the register; otherwise it says why the value is
    of doubtful kind (`info_unsure`: the context does not tell what the register hid; `info_civil_org`: a civil body
    or a company, which identifies no natural person). A model trained on the output should ignore masked spans
    rather than learn them as either personal data or plain text.
    """
    start: int
    end: int
    label: str
    placeholder: str
    text: str
    subtype: str | None = None
    mask: str | None = None

    @property
    def masked(self) -> bool:
        return self.mask is not None


@dataclass
class FilledDocument:
    """A pseudonymized text with its placeholders replaced by synthetic values."""
    text: str
    source: str
    entities: list[Entity] = field(default_factory=list)
    id: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def labels(self) -> list[Entity]:
        """The entities that are personal data (not masked)."""
        return [e for e in self.entities if e.mask is None]

    @property
    def masks(self) -> list[Entity]:
        """The entities of doubtful kind, see Entity.mask."""
        return [e for e in self.entities if e.mask is not None]

    def persons(self) -> dict[str, list[str]]:
        """Each ОСОБА placeholder and the mentions written for it, in text order."""
        out: dict[str, list[str]] = {}
        for e in self.entities:
            if e.label == PERSON:
                out.setdefault(e.placeholder, []).append(e.text)
        return out

    def to_dict(self) -> dict:
        """JSON-ready: `text`, `source`, `annotations` (labels) and `masks`, each span with `start`, `end`, `type`,
        `placeholder`, `text`, `subtype` (and `reason` for a mask)."""
        def span(e: Entity) -> dict:
            out = {"start": e.start, "end": e.end, "type": e.label, "placeholder": e.placeholder, "text": e.text, "subtype": e.subtype}
            if e.mask is not None:
                out["reason"] = e.mask
            return out
        return {"id": self.id, "text": self.text, "source": self.source, "annotations": [span(e) for e in self.labels],
                "masks": [span(e) for e in self.masks], **({"meta": self.meta} if self.meta else {})}

    def to_spacy(self, include_masked: bool = False) -> tuple[str, dict]:
        """(text, {"entities": [(start, end, label), …]}), the training format of spaCy 2 and many NER tools."""
        ents = [(e.start, e.end, e.label) for e in self.entities if include_masked or e.mask is None]
        return self.text, {"entities": ents}

    def highlight(self, mark: str = "[{text}|{label}]") -> str:
        """The text with every entity written through `mark` («[Шевченко Тарас Григорович|ОСОБА]»), for reading."""
        out, pos = [], 0
        for e in sorted(self.entities, key=lambda e: e.start):
            out += [self.text[pos:e.start], mark.format(**asdict(e), masked=e.masked)]
            pos = e.end
        return "".join(out + [self.text[pos:]])

    def __str__(self) -> str:
        return self.text
