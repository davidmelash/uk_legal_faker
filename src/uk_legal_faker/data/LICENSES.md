# Data files and their licences

The code of uk-legal-faker is under the MIT licence (`LICENSE` at the root of the repository). The data files in this
folder come from other projects and keep their own licences. Each one is a separate file that the code reads; none is
compiled into the code.

| file | what it is | source | licence |
|---|---|---|---|
| `names.json.gz` | 276 male and 294 female first names, 400 patronymics of each gender, 2,500 surnames, with weights (square root of the corpus frequency); built by `scripts/build_names.py` | [lang-uk/name_freq_dict_uk](https://github.com/lang-uk/name_freq_dict_uk), `generated/*.csv` | GNU GPL v3.0 |
| `addresses_osm.tsv.gz` | 71,948 streets of 8,580 settlements with up to 8 house numbers each, region, district, city district, postal index where known | [OpenStreetMap](https://www.openstreetmap.org/copyright), Geofabrik extract of Ukraine of 2026-10-08, built by `scripts/build_osm_addresses.py` | © OpenStreetMap contributors, [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |
| `decisions.jsonl.gz` | 60 pseudonymized court decisions of 2024 (templates of `LegalFaker.court_decision`) | [lang-uk/court-decisions-uk](https://huggingface.co/datasets/lang-uk/court-decisions-uk), from the Unified State Register of Court Decisions (ЄДРСР) | MIT (dataset); court decisions are official documents, not subject to copyright (Law of Ukraine «On Copyright and Related Rights», art. 18) |

When you publish a dataset built with the bundled addresses, credit «© OpenStreetMap contributors» and keep the
address data under the ODbL. When you redistribute `names.json.gz`, keep it under the GPL v3.0.

`uk-legal-faker data ukrposhta` builds a third table, the Ukrposhta directory of postal addresses, on your own machine
(it is downloaded from ukrposhta.ua and never bundled: the directory is published without an open licence). Check its
terms before you publish data built with it.
