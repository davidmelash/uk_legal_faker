"""A tour of uk-legal-faker: python examples/quickstart.py"""
from uk_legal_faker import LegalFaker

fake = LegalFaker(seed=42)

print("— persons —")
person = fake.person()
for case in ("nomn", "gent", "datv", "accs", "ablt"):
    print(f"{case}: {person.name(case)}")
print("initials:", person.name(form="initials"))

print("\n— addresses —")
print(fake.address())
print(fake.address(region="Одеська"))
print("born in", fake.settlement())

print("\n— identifiers —")
for method in ("rnokpp", "passport", "iban", "phone", "license_plate", "vin", "military_unit_code", "enforcement_proceeding_number"):
    print(f"{method}: {getattr(fake, method)()}")

print("\n— organisations —")
print(fake.military_body("gent"))
print(fake.tck("datv"))
print(fake.civil_body())
print(fake.company("ablt"))

print("\n— a filled decision —")
doc = fake.court_decision("військові")
print(doc.highlight()[:1500], "…")
print(f"\n{len(doc.labels)} labelled values, {len(doc.masks)} masked; persons: {doc.persons()}")
