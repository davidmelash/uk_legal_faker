# Changelog

## 0.1.0 (2026-10-19)

First release, packaged from the silver-data generator of a court-decision pseudonymization project.

- `LegalFaker`: names declined by case, addresses of real streets (OpenStreetMap, optionally the Ukrposhta
  directory), identifiers (РНОКПП, passports, IBAN, phones, plates, VIN, IMEI, unit codes, enforcement proceedings),
  dates, e-mails and links, military and civil bodies, companies, banks and courts declined by case.
- `fill()`: replaces ОСОБА / АДРЕСА / НОМЕР / ІНФОРМАЦІЯ placeholders by context and returns character spans, with
  masks for values of doubtful kind.
- `court_decision()`: 60 bundled pseudonymized decisions of 2024, filled.
- Faker provider (`uk_legal_faker.provider.UkrainianLegalProvider`) and the `uk-legal-faker` command.
- Changes from the original generator: the gender of a person is a vote over every mention, including the verb after
  it; a person right after a noun is in the genitive and right after a conjunction in the nominative; the short
  dative after a hushing consonant («Іллічу», not «Іллічю»); first-name lists without surnames, place names and
  invented names.
