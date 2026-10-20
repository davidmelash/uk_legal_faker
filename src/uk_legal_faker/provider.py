"""A provider for the Faker library (`pip install uk-legal-faker[faker]`).

    from faker import Faker
    from uk_legal_faker.provider import UkrainianLegalProvider

    fake = Faker("uk_UA")
    fake.add_provider(UkrainianLegalProvider)
    Faker.seed(0)
    fake.legal_name(case="datv")
    fake.legal_court_decision().text

Every method draws from Faker's own random generator, so `Faker.seed()` and `seed_instance()` make it reproducible.
The methods carry the `legal_` prefix so that they do not shadow Faker's own `name`, `address`, `iban`, ….
"""
from __future__ import annotations

import datetime as dt

from faker.providers import BaseProvider

from uk_legal_faker.document import FilledDocument
from uk_legal_faker.generator import LegalFaker


class UkrainianLegalProvider(BaseProvider):
    """Faker methods of uk-legal-faker; see LegalFaker for what each one returns."""

    def _legal(self) -> LegalFaker:
        rng = self.generator.random
        if getattr(self, "_legal_rng", None) is not rng:  # Faker replaces its generator on seed_instance()
            self._legal_faker = LegalFaker(rng=rng)
            self._legal_rng = rng
        return self._legal_faker

    # persons
    def legal_name(self, case: str = "nomn", gender: str | None = None, form: str = "full") -> str:
        return self._legal().name(case, gender, form)

    # addresses
    def legal_address(self, region: str | None = None) -> str:
        return self._legal().address(region)

    def legal_settlement(self, region: str | None = None) -> str:
        return self._legal().settlement(region)

    # numbers
    def legal_rnokpp(self) -> str:
        return self._legal().rnokpp()

    def legal_passport(self) -> str:
        return self._legal().passport()

    def legal_iban(self) -> str:
        return self._legal().iban()

    def legal_bank_card(self) -> str:
        return self._legal().bank_card()

    def legal_phone(self) -> str:
        return self._legal().phone()

    def legal_imei(self) -> str:
        return self._legal().imei()

    def legal_certificate_number(self) -> str:
        return self._legal().certificate_number()

    def legal_military_unit_code(self) -> str:
        return self._legal().military_unit_code()

    def legal_vin(self) -> str:
        return self._legal().vin()

    def legal_license_plate(self) -> str:
        return self._legal().license_plate()

    def legal_enforcement_proceeding_number(self) -> str:
        return self._legal().enforcement_proceeding_number()

    # dates
    def legal_date_of_birth(self, minor: bool = False) -> dt.date:
        return self._legal().date_of_birth(minor)

    def legal_birth_date(self, minor: bool = False, style: str | None = None) -> str:
        return self._legal().birth_date(minor, style)

    # internet
    def legal_email(self) -> str:
        return self._legal().email()

    def legal_url(self, kind: str = "page") -> str:
        return self._legal().url(kind)

    def legal_social_account(self) -> str:
        return self._legal().social_account()

    # organisations
    def legal_military_unit(self, case: str = "nomn") -> str:
        return self._legal().military_unit(case)

    def legal_military_body(self, case: str = "nomn") -> str:
        return self._legal().military_body(case)

    def legal_tck(self, case: str = "nomn") -> str:
        return self._legal().tck(case)

    def legal_civil_body(self, case: str = "nomn") -> str:
        return self._legal().civil_body(case)

    def legal_company(self, case: str = "nomn") -> str:
        return self._legal().company(case)

    def legal_bank(self) -> str:
        return self._legal().bank()

    def legal_court(self, case: str = "nomn") -> str:
        return self._legal().court(case)

    # documents
    def legal_fill(self, text: str) -> FilledDocument:
        return self._legal().fill(text)

    def legal_court_decision(self, kind: str | None = None) -> FilledDocument:
        return self._legal().court_decision(kind)
