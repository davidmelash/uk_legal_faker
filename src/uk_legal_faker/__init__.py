"""uk-legal-faker: synthetic personal data for Ukrainian court decisions.

    from uk_legal_faker import LegalFaker

    fake = LegalFaker(seed=42)
    fake.name(case="gent")          # a full name in the genitive
    fake.address()                  # a real street and house in Ukraine
    fake.rnokpp()                   # a 10-digit taxpayer number
    doc = fake.fill("Позов ОСОБА_1 до ІНФОРМАЦІЯ_1 про стягнення")
    doc.text, doc.entities          # filled text and character spans
"""
from uk_legal_faker.document import ADDRESS, ENTITY_TYPES, INFO, NUMBER, PERSON, Entity, FilledDocument, find_placeholders, normalize
from uk_legal_faker.filler import Filler
from uk_legal_faker.generator import ORG_KINDS, LegalFaker
from uk_legal_faker.morph import CASES, inflect, inflect_full
from uk_legal_faker.orgs import Org, inflect_phrase
from uk_legal_faker.persons import FORMS, Person

__version__ = "0.1.0"

__all__ = ["ADDRESS", "CASES", "ENTITY_TYPES", "FORMS", "INFO", "NUMBER", "ORG_KINDS", "PERSON", "Entity", "FilledDocument", "Filler",
           "LegalFaker", "Org", "Person", "__version__", "find_placeholders", "inflect", "inflect_full", "inflect_phrase", "normalize"]
