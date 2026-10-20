# uk-legal-faker

[![CI](https://github.com/davidmelash/uk_legal_faker/actions/workflows/ci.yml/badge.svg)](https://github.com/davidmelash/uk_legal_faker/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)

Synthetic personal data for Ukrainian court decisions. You get names declined by grammatical case, addresses of real
streets and houses, identifiers in the formats the courts use, military and civil bodies, and real pseudonymized
decisions with every placeholder filled.

```python
from uk_legal_faker import LegalFaker

fake = LegalFaker(seed=7)
doc = fake.fill(
    "Позивач ОСОБА_1 , ІНФОРМАЦІЯ_1 року народження, РНОКПП НОМЕР_1 , зареєстрований за адресою: АДРЕСА_1 , "
    "звернувся до суду з позовом до ІНФОРМАЦІЯ_2 про визнання протиправною бездіяльності. "
    "Зобов'язати ІНФОРМАЦІЯ_2 нарахувати ОСОБА_1 грошове забезпечення."
)
print(doc.highlight())
```

```
Позивач [Щербань Данило Михайлович|ОСОБА], [1998-01-03|ІНФОРМАЦІЯ] року народження, РНОКПП [2613186091|НОМЕР],
зареєстрований за адресою: [м. Запоріжжя, вул. Козача, буд. 5, кв. 39, Запорізька область|АДРЕСА], звернувся до суду
з позовом до [Служби безпеки України|ІНФОРМАЦІЯ] про визнання протиправною бездіяльності. Зобов'язати [Службу безпеки
України|ІНФОРМАЦІЯ] нарахувати [Щербаня Данила Михайловича|ОСОБА] грошове забезпечення.
```

Each value fits the words around it. The person stays the same across mentions and is declined as each mention needs
(«Щербань Данило Михайлович», «Щербаня Данила Михайловича»). The body is a party to a serviceman's case, so it is a
military one, written in the genitive after «до» and in the accusative after «зобов'язати». The birth date is followed
by the text's own «року», so the date does not repeat the word. Every value comes with its character span. You can use
the output to train and test NER, pseudonymization and de-identification models for Ukrainian legal text.

## Why

The Unified State Register of Court Decisions (ЄДРСР) publishes millions of decisions. In each one, personal data is
replaced by placeholders: `ОСОБА_1` (a person), `АДРЕСА_1` (an address), `НОМЕР_1` (an identifier) and
`ІНФОРМАЦІЯ_1` (anything else, such as a birth date, an e-mail or the name of a military unit). That makes a large
corpus of real legal text that shows exactly where the personal data was, but not what it looked like. This library
puts realistic values back, so the corpus becomes labelled training data.

General-purpose fakers do not do this well for Ukrainian. Names have to be declined into six cases. Institutions are
long noun phrases where only the head declines («Головного управління Пенсійного фонду України в Одеській області»).
Courts write identifiers in many formats («серії КВ № 123456», «UA21 3052 9900 0002 6…»). A date «до досягнення
дитиною повноліття, тобто до …» has to be the child's birth date plus 18 years.

## Install

```bash
pip install uk-legal-faker            # Python 3.10+
pip install "uk-legal-faker[faker]"   # with the Faker provider
```

The only dependencies are `pymorphy3` and its Ukrainian dictionary. All data is bundled (about 1.2 MB), and nothing is
downloaded at run time.

## Single values

```python
fake = LegalFaker(seed=42)

fake.name()                      # 'Самусь Володимир Ілліч'
fake.name(case="datv")           # dative: 'Самусю Володимиру Іллічу'
fake.name(form="initials")       # 'Самусь В.І.'
p = fake.person("femn")          # one identity, any case or form: p.name("gent"), p.name("ablt", "initials")

fake.address()                   # 'вул. Сонячна, 12/2, кв. 15, м. Запоріжжя, Запорізька область, 69000'
fake.address(region="Львівська") # 'по вул. Ліська, 3, м. Львів, Львівська область'
fake.settlement()                # place of birth: 'с. Іванівка Полтавської області'

fake.rnokpp()                    # '3192832764'
fake.passport()                  # 'серії КВ № 123456' / '935030564 (УНЗР 19900101-01234)'
fake.iban()                      # 'UA593282090000026978480184514'
fake.phone()                     # '+38 (067) 123-45-67'
fake.license_plate()             # 'АА 1234 ВС' / 'EP 9570 PA'
fake.vin(), fake.imei(), fake.bank_card(), fake.certificate_number()
fake.military_unit_code()        # 'А1234'
fake.enforcement_proceeding_number()

fake.date_of_birth(minor=True)   # datetime.date, 1-17 years before ref_year
fake.birth_date(style="words")   # '14 червня 1990'
fake.email(), fake.url("profile"), fake.social_account(), fake.login()

fake.military_unit("gent")       # 'Окремої бригади територіальної оборони «Сокіл»'
fake.military_unit_name()        # '72 окрема механізована бригада', 'Оперативне командування «Захід»'
fake.military_body("datv")       # 'Полтавському районному територіальному центру комплектування та соціальної підтримки'
fake.tck(), fake.civil_body(), fake.company("gent"), fake.company_name(), fake.bank(), fake.court(),
fake.prosecutors_office(), fake.police_unit(), fake.hospital()

org = fake.org("tck")            # an Org renders itself in any case
org.render("loct")               # 'Дарницькому районному у місті Києві територіальному центрі комплектування …'
```

Cases are `nomn`, `gent`, `datv`, `accs` and `ablt`. Organisations also take `loct`.

## Filling decisions

`fill()` takes any text with ЄДРСР placeholders and returns a `FilledDocument`:

```python
doc = fake.fill(text)               # text: the pseudonymized decision
doc.text                            # the filled text
doc.source                          # the input after spacing normalization («ОСОБА_1 ,» -> «ОСОБА_1,»)
doc.entities                        # [Entity(start, end, label, placeholder, text, subtype, mask), …]
doc.labels, doc.masks               # entities that are personal data / of doubtful kind (see below)
doc.persons()                       # {'ОСОБА_1': ['Щербань Данило Михайлович', 'Щербаня Данила Михайловича']}
doc.to_dict()                       # JSON-ready: text, source, annotations, masks
doc.to_spacy()                      # (text, {"entities": [(start, end, label), …]})
doc.highlight()                     # the text with [value|LABEL] marks
```

`fake.court_decision()` fills one of 60 bundled decisions from 2024 (Supreme Court, civil, administrative,
servicemen's, criminal and commercial cases; `kind="КАС"` and so on). `fake.templates()` lists them.

**One identity per placeholder.** Every mention of `ОСОБА_1` is the same person, and every mention of `АДРЕСА_2` is
the same address (later mentions sometimes switch between «вул.» and «вулиця»). The gender of a person is a vote over
the words before its mentions («позивачка», «сина») and the verbs after them («звернулася», «перебував»).

**Values that agree with the text.** Addresses lie in the region the decision is about, and in a settlement it names
when it names one. One address style and one date format hold for the whole document. A body that the decision
already names in the open is never drawn for a placeholder. A short name after «(далі - …)» is built from the body
before the bracket («військової частини А5885 (далі - в/ч А5885)»). Derived dates follow the birth dates they are
computed from.

**Reproducible.** The same `seed` gives the same output. Pass `doc_id=` and the values depend only on the seed and the
id, not on what was filled before. You can then refill one document of a corpus without changing the others.
`version=2` fills the same document again with different values.

### Masks: values of doubtful kind

For some ІНФОРМАЦІЯ placeholders the context does not say what the register hid. Examples are a bare «ІНФОРМАЦІЯ_3»
with no cue nearby, a login, a surname in quotes, or the body of a judge. The library still writes a natural value
there, so the text reads well, but it marks the entity with `mask="info_unsure"`. Civil bodies, companies, banks and
hospitals that fill a hidden slot get `mask="info_civil_org"`. They identify no natural person, and most decisions
name them in the open. When you train a model, ignore masked spans (for example, give them the label `-100`) instead
of teaching them as either personal data or plain text. Use `doc.labels` if you only want certain personal data.

[docs/filling.md](docs/filling.md) lists the sub-types and the rules that choose them.

## Faker provider

```python
from faker import Faker
from uk_legal_faker.provider import UkrainianLegalProvider

fake = Faker("uk_UA")
fake.add_provider(UkrainianLegalProvider)
Faker.seed(0)

fake.legal_name(case="gent")
fake.legal_address()
fake.legal_rnokpp()
fake.legal_military_body("datv")
fake.legal_court_decision().text
```

The methods have the `legal_` prefix so they do not shadow Faker's own `name`, `address` or `iban`. They draw from
Faker's random generator, so `Faker.seed()` and `seed_instance()` make them reproducible.

## Command line

```bash
uk-legal-faker generate name --case gent -n 3
uk-legal-faker generate address --region Одеська -n 5
uk-legal-faker sample -n 100 -o decisions.jsonl                 # filled bundled decisions, JSONL with spans
uk-legal-faker sample --kind ГПК --format highlight
uk-legal-faker fill corpus.jsonl -o filled.jsonl --versions 2   # your own pseudonymized texts ({"id", "text"} per line)
uk-legal-faker fill decision.txt --format text
uk-legal-faker data ukrposhta                                   # optional: build the Ukrposhta address table
```

## Building a training set

```python
import json
from uk_legal_faker import LegalFaker

fake = LegalFaker(seed=1)
with open("pseudonymized.jsonl") as src, open("train.jsonl", "w") as out:
    for line in src:
        row = json.loads(line)
        doc = fake.fill(row["text"], doc_id=row["id"])
        out.write(json.dumps(doc.to_dict(), ensure_ascii=False) + "\n")
```

For a corpus, the dataset [lang-uk/court-decisions-uk](https://huggingface.co/datasets/lang-uk/court-decisions-uk)
has 2024 decisions with placeholders. [examples/](examples/) has a runnable version of this example that also writes
token-level BIO tags.

Only the placeholders are annotated. Decisions also name judges, lawyers and officials in the open. Those names stay
in the text without labels, so tag them in a separate pass if your task needs it.

## Data

| table | rows | source | licence |
|---|---|---|---|
| names | 276 + 294 first names, 400 + 400 patronymics, 2,500 surnames | [lang-uk/name_freq_dict_uk](https://github.com/lang-uk/name_freq_dict_uk) | GPL-3.0 |
| addresses | 71,948 streets of 8,580 settlements, with real house numbers | © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors | ODbL 1.0 |
| decision templates | 60 pseudonymized decisions of 2024 | [lang-uk/court-decisions-uk](https://huggingface.co/datasets/lang-uk/court-decisions-uk) | MIT |
| Ukrposhta addresses (optional) | 330,000 streets of 25,600 settlements | ukrposhta.ua, built locally by `uk-legal-faker data ukrposhta` | no open licence: not bundled |

Military bodies, ТЦК, units, civil bodies and companies are composed from word lists in the code. With
`LegalFaker(org_names="names.tsv")` you can replace a share of the civil bodies and companies with real names.
[docs/data.md](docs/data.md) describes the table formats, the cache directory and how each bundled file was built
(`scripts/`).

When you publish data generated with the bundled addresses, credit «© OpenStreetMap contributors». See
[src/uk_legal_faker/data/LICENSES.md](src/uk_legal_faker/data/LICENSES.md).

## Limitations

- The gender of a person is guessed from role words and past-tense verbs next to its mentions. When there are none, it
  is random, and an adjective further away («кухаря …, зареєстрованого») can disagree with it.
- Inflection uses pymorphy3 with suffix rules as a fallback. Rare surnames can come out in an unusual form.
- The ІНФОРМАЦІЯ rules were measured on decisions of 2024. On other kinds of text, expect more masked values.
- Dates count from `ref_year` (default 2024). Pass `LegalFaker(ref_year=…)` for documents from other years.

## Development

```bash
git clone https://github.com/davidmelash/uk_legal_faker && cd uk_legal_faker
uv sync                       # or: pip install -e . pytest ruff faker
uv run pytest
uv run ruff check src tests scripts
```

The library grew out of the silver-data generator of a Ukrainian court-decision pseudonymization project. Its context
rules were checked against about 2,300 hand-labelled ІНФОРМАЦІЯ placeholders.

## Licence

The code is released under the [MIT licence](LICENSE). You may use, copy, modify, merge, publish, distribute,
sublicense and sell it, for any purpose, commercial or not. The only condition is that the copyright notice stays
with copies of the code.

The bundled data files come from other projects and keep their own licences. The address table is under the ODbL:
any use is allowed, with credit to «© OpenStreetMap contributors». The name list is under the GPL-3.0, which applies
when you redistribute that file. Details are in [LICENSES.md](src/uk_legal_faker/data/LICENSES.md).
