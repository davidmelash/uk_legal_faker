# Data

## Bundled files

All bundled files are in `src/uk_legal_faker/data/` and are gzip-compressed. The scripts in `scripts/` rebuild them.

| file | built by | contents |
|---|---|---|
| `names.json.gz` | `scripts/build_names.py` | `{"male_first" \| "female_first" \| "male_patr" \| "female_patr" \| "surname": [[name, weight], …]}` |
| `addresses_osm.tsv.gz` | `scripts/build_osm_addresses.py` | the address table described below |
| `decisions.jsonl.gz` | `scripts/build_templates.py` | one decision per line: `id`, `kind`, `case`, `source`, `text` |

`build_osm_addresses.py` needs `osmium` and `shapely` and downloads 880 MB. `build_templates.py --check` refetches
the source texts of the bundled templates and compares them.

## Address tables

The address generator reads one or more tables with these tab-separated columns (a header line is required, and the
order of the columns is free):

| column | example | note |
|---|---|---|
| `region` | `Львівська` | the adjective without «область»; `Київ` for the city |
| `district_old` | `Стрийський` | district before the 2020 reform (may be empty) |
| `district_new` | `Стрийський` | district after the reform |
| `np_type` | `м.` | `м.` city, `с.` village, `с-ще` town |
| `np` | `Моршин` | settlement |
| `zip` | `82482` | postal index (may be empty) |
| `st_type` | `вул.` | `вул.`, `пров.`, `просп.`, `бульв.`, `пл.`, `проїзд`, `узвіз`, `майдан`, `шосе`, `тупик`, `в’їзд`, `м-р`, `кв-л` |
| `street` | `Шевченка` | street name |
| `houses` | `1,3,5А,12/2` | real house numbers, comma-separated |
| `city_district` | `Шевченківський` | district of a city (may be empty) |

Rows with another settlement or street type, or with no houses, are skipped. The generator chooses tables like this:

```python
LegalFaker()                                          # Ukrposhta when it was built, then OpenStreetMap
LegalFaker(address_sources=["osm"])                   # the bundled table only
LegalFaker(address_sources=["my_addresses.tsv.gz"])   # your own table
```

The first table that knows a settlement fixes its spelling, type and districts. When a later table has the same
settlement (same region, name and district), its rows are added to that settlement, and an address comes from them
with probability `P_OSM` (0.3).

### The Ukrposhta directory

```bash
uk-legal-faker data ukrposhta                    # downloads houses.zip (6 MB) from ukrposhta.ua
uk-legal-faker data ukrposhta --source houses.zip
```

This writes `ukrposhta.tsv.gz` (about 330,000 streets of 25,600 settlements) to the cache directory. That is
`$UK_LEGAL_FAKER_HOME` if set, else `$XDG_CACHE_HOME/uk-legal-faker`, else `~/.cache/uk-legal-faker`. From then on,
`LegalFaker()` uses it before the bundled OpenStreetMap table. The directory is published without an open licence,
so it is not bundled. Check its terms before you publish data built with it.

## Real organisation names

The organisation generator composes names from word lists. A table of real names can replace a share of the civil
bodies and companies: `LegalFaker(org_names=path_or_dict)`. The file is a TSV (or a CSV, by the `.csv` extension)
with the columns `source`, `kind` and `name`. A dict maps `(source, kind)` to a list of names.

| source, kind | used for | share |
|---|---|---|
| `court`, `company` | company names in any decision | 60 % of company names |
| `edr`, `company` | company names in commercial decisions (register of legal entities) | half of the real company names there |
| `court`, `body` | central and regional state bodies | 50 % |
| `treasury`, `social` | social-protection bodies in servicemen's and social cases | 60 % |
| `treasury`, `prosecutor` | prosecutor's offices in servicemen's and social cases | |

Names that look like a person's name («Іванов І.І.», «Іванова Івана Івановича») and names shorter than three letters
are left out. A real name is declined like a composed one: the words up to its head noun follow the case. Military
bodies always come from the word lists, because no public register names them.
