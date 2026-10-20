"""The public API: LegalFaker, FilledDocument, the Faker provider and the command line."""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import sys

import pytest

from uk_legal_faker import CASES, ENTITY_TYPES, FORMS, ORG_KINDS, LegalFaker, Person, find_placeholders
from uk_legal_faker.cli import GENERATORS, main
from uk_legal_faker.document import PLACEHOLDER

TEXT = ("Позивач ОСОБА_1 , ІНФОРМАЦІЯ_1 , РНОКПП НОМЕР_1 , мешкає за адресою: АДРЕСА_1 , звернувся до суду з позовом до "
        "ІНФОРМАЦІЯ_2 про стягнення. Представник ОСОБА_1 просив стягнути з ІНФОРМАЦІЯ_2 на користь ОСОБА_1 кошти.")


def test_same_seed_same_values_other_seed_other_values():
    def draw(seed):
        f = LegalFaker(seed)
        return [f.name(), f.address(), f.rnokpp(), f.military_body("gent"), f.email(), f.fill(TEXT).text]
    assert draw(5) == draw(5)
    assert draw(5) != draw(6)


@pytest.mark.parametrize("case", CASES)
def test_name_in_every_case(case):
    f = LegalFaker(1)
    for _ in range(30):
        assert re.fullmatch(r"[А-ЯІЇЄҐ][\w'’ʼ-]+ [А-ЯІЇЄҐ][\w'’ʼ-]+ [А-ЯІЇЄҐ][\w'’ʼ-]+", f.name(case=case))


def test_person_renders_every_form_and_a_short_dative():
    p = Person("masc", "Шевченко", "Тарас", "Григорович")
    assert p.name("gent") == "Шевченка Тараса Григоровича"
    assert p.name("datv") == "Шевченку Тарасу Григоровичу"
    assert [p.name("nomn", form) for form in FORMS] == ["Шевченко Тарас Григорович", "Шевченко Т.Г.", "Шевченко Т.", "Тарас Шевченко",
                                                        "Т.Г. Шевченко"]
    assert Person("femn", "Шевченко", "Олена", "Петрівна").name("datv") == "Шевченко Олені Петрівні"
    assert Person("masc", "Самусь", "Ігор", "Ілліч").name("datv") == "Самусю Ігорю Іллічу"
    assert Person("masc", "Коваль", "Андрій", "Кузьмич").name("datv") == "Ковалю Андрію Кузьмичу"
    with pytest.raises(ValueError):
        p.name("vocative")


def test_gender_is_kept():
    f = LegalFaker(2)
    assert all(f.person("femn").patr.endswith("на") for _ in range(50))
    assert all(f.person("masc").patr.endswith("ич") for _ in range(50))
    with pytest.raises(ValueError):
        f.person("x")


def test_address_in_a_region():
    f = LegalFaker(3)
    assert "Київ" in f.regions and "Львівська" in f.regions
    lviv = [f.address(region="Львівська") for _ in range(100)]
    assert sum("Львів" in a for a in lviv) > 50
    with pytest.raises(ValueError):
        f.address(region="Atlantis")


def test_identifiers_have_their_shapes():
    f = LegalFaker(4)
    for _ in range(50):
        assert re.fullmatch(r"\d{10}", f.rnokpp())
        assert re.fullmatch(r"UA\d{27}", f.iban().replace(" ", ""))
        assert re.fullmatch(r"\d{4} \d{4} \d{4} \d{4}", f.bank_card())
        assert re.fullmatch(r"\d{15}", f.imei())
        assert re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", f.vin())
        assert re.fullmatch(r"[АВТA]І?\d{4}", f.military_unit_code())
        assert re.sub(r"\D", "", f.phone())[-9:].isdigit()


def test_dates():
    f = LegalFaker(5, ref_year=2030)
    assert f.ref_year == 2030
    assert all(2030 - 17 <= f.date_of_birth(minor=True).year <= 2029 for _ in range(100))
    assert all(f.date_of_birth().year <= 2030 - 18 for _ in range(100))
    born = dt.date(1990, 5, 1)
    assert all(f.date_of_death(born=born) > born for _ in range(100))
    assert all(f.date_of_death(war=True) >= dt.date(2022, 2, 24) for _ in range(100))
    d = dt.date(2001, 5, 17)
    assert [f.format_date(d, s) for s in ("iso", "numeric", "words", "words_roku")] == [
        "2001-05-17", "17.05.2001", "17 травня 2001", "17 травня 2001 року"]
    with pytest.raises(ValueError):
        f.format_date(d, "roman")


def test_internet_values():
    f = LegalFaker(6)
    assert all(re.fullmatch(r"[\w.]+@[\w.-]+\.\w+", f.email()) for _ in range(50))
    assert all(re.match(r"(https?://)?(www\.)?[\w.-]+\.\w+", f.url(kind)) for kind in ("site", "page", "profile") for _ in range(20))
    with pytest.raises(ValueError):
        f.url("ftp")


@pytest.mark.parametrize("kind", ORG_KINDS)
def test_every_org_kind_renders_in_every_case(kind):
    f = LegalFaker(7)
    for _ in range(10):
        org = f.org(kind)
        assert all(org.render(case) for case in ("nomn", "gent", "datv", "accs", "ablt", "loct"))


def test_org_methods_decline():
    f = LegalFaker(8)
    assert f.org("military_body") is not None
    tck = [f.tck("gent") for _ in range(30)]
    assert any("територіального центру комплектування" in t for t in tck)
    with pytest.raises(ValueError):
        f.org("church")


def test_fill_gives_offsets_into_the_filled_text():
    doc = LegalFaker(9).fill(TEXT)
    assert not PLACEHOLDER.search(doc.text) and " ," not in doc.text
    assert {e.label for e in doc.entities} == set(ENTITY_TYPES)
    for e in doc.entities:
        assert doc.text[e.start:e.end] == e.text and e.text == e.text.strip()
    persons = doc.persons()
    assert set(persons) == {"ОСОБА_1"} and len(persons["ОСОБА_1"]) == 3
    assert next(e for e in doc.entities if e.placeholder == "НОМЕР_1").subtype == "rnokpp"
    d = doc.to_dict()
    assert json.loads(json.dumps(d, ensure_ascii=False)) == d
    assert len(d["annotations"]) + len(d["masks"]) == len(find_placeholders(doc.source))
    text, ann = doc.to_spacy()
    assert text == doc.text and len(ann["entities"]) == len(doc.labels)
    assert "|ОСОБА]" in doc.highlight()


def test_fill_with_an_id_does_not_depend_on_earlier_documents():
    a, b = LegalFaker(10), LegalFaker(10)
    b.fill(TEXT, doc_id="other")
    b.name()
    assert a.fill(TEXT, doc_id="x").text == b.fill(TEXT, doc_id="x").text
    assert a.fill(TEXT, doc_id="x").text != a.fill(TEXT, doc_id="x", version=2).text


@pytest.mark.parametrize("tpl", LegalFaker.templates(), ids=lambda t: t["id"])
def test_every_template_fills_cleanly(tpl):
    f = LegalFaker(11)
    doc = f.fill(tpl["text"], doc_id=tpl["id"], kind=tpl["kind"], normalize_text=False)
    assert not PLACEHOLDER.search(doc.text)
    assert len(doc.entities) == len(find_placeholders(tpl["text"]))
    for e in doc.entities:
        assert doc.text[e.start:e.end] == e.text and e.text.strip() == e.text and "None" not in e.text


def test_court_decision():
    f = LegalFaker(12)
    kinds = {t["kind"] for t in f.templates()}
    assert kinds == {"ВС", "ЦПК", "КАС", "військові", "КПК", "ГПК"}
    doc = f.court_decision("КАС")
    assert doc.id and doc.meta["source"].startswith("lang-uk/court-decisions-uk") and doc.entities
    with pytest.raises(ValueError):
        f.court_decision("XYZ")


def test_real_org_names_from_a_file(tmp_path):
    path = tmp_path / "names.tsv"
    path.write_text("source\tkind\tname\ncourt\tcompany\tРеальна Компанія\ncourt\tcompany\tІванов Іван Іванович\n", encoding="utf-8")
    f = LegalFaker(13, org_names=path)
    names = {f.company_name() for _ in range(200)}
    assert "Реальна Компанія" in names and "Іванов Іван Іванович" not in names  # a person's name is never drawn


def test_faker_provider_follows_fakers_seed():
    faker = pytest.importorskip("faker")
    from uk_legal_faker.provider import UkrainianLegalProvider

    fake = faker.Faker("uk_UA")
    fake.add_provider(UkrainianLegalProvider)

    def draw():
        return [fake.legal_name(case="gent"), fake.legal_address(), fake.legal_rnokpp(), fake.legal_military_unit("datv"),
                fake.legal_court_decision().text[:200]]
    fake.seed_instance(1)
    first = draw()
    fake.seed_instance(1)
    assert draw() == first
    fake.seed_instance(2)
    assert draw() != first
    assert fake.name()  # Faker's own methods are untouched


def test_cli_generate_sample_and_fill(tmp_path, capsys):
    for what in sorted(GENERATORS):
        main(["generate", what, "-n", "2", "--seed", "1"] + (["--case", "gent"] if GENERATORS[what] else []))
        assert len(capsys.readouterr().out.strip().splitlines()) == 2, what
    main(["sample", "-n", "2", "--seed", "1"])
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 2 and all(r["annotations"] for r in rows)
    src = tmp_path / "in.jsonl"
    src.write_text(json.dumps({"id": "a", "text": TEXT, "kind": "ЦПК"}, ensure_ascii=False) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    main(["fill", str(src), "-o", str(out), "--seed", "3", "--versions", "2", "--keep-fields"])
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in rows] == ["a", "a"] and rows[0]["text"] != rows[1]["text"] and rows[0]["kind"] == "ЦПК"
    with pytest.raises(SystemExit):
        main(["generate", "address", "--region", "Atlantis"])


def test_cli_writes_utf8_on_a_console_without_cyrillic(monkeypatch):
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding="cp1252")  # the Windows default
    monkeypatch.setattr(sys, "stdout", console)
    main(["generate", "name", "-n", "1", "--seed", "1"])
    console.flush()
    assert re.fullmatch(r"[А-ЯІЇЄҐ][\w'’ʼ -]+\n", raw.getvalue().decode("utf-8").replace("\r", ""))
