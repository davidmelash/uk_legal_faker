"""Shared helpers: the tests that came from the dataset pipeline work on document dicts; LegacyFiller adapts them."""
from __future__ import annotations

from uk_legal_faker.filler import Filler


class LegacyFiller(Filler):
    """Filler.fill on a {"id", "text", "placeholders", "kind"} dict, returning {"text", "labels", "masks", …} with the
    offsets of the labels and masks, as the dataset pipeline wrote them."""

    def fill(self, doc, fill: int = 1, **kw):  # type: ignore[override]
        if isinstance(doc, str):
            return super().fill(doc, **kw)
        out = super().fill(doc["text"], doc_id=doc["id"], kind=doc.get("kind"), version=fill, normalize_text=False)
        return {"id": doc["id"], "fill": fill, "text": out.text, "text_pseudonymized": out.source,
                "labels": [{"start": e.start, "end": e.end, "type": e.label, "pseudonym": e.placeholder, "source": "placeholder"} for e in out.labels],
                "masks": [{"start": e.start, "end": e.end, "reason": e.mask} for e in out.masks], "n_persons": out.meta["n_persons"]}
