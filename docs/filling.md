# How filling works

`LegalFaker.fill(text)` (or `Filler.fill`) reads a pseudonymized decision once from left to right. For each
placeholder it chooses a value from the words around it. This page describes those choices. The code is in
`src/uk_legal_faker/filler.py`, and the rules are in `context.py`.

## The four placeholder types

| placeholder | value | how the context is read |
|---|---|---|
| `ОСОБА_n` | surname, first name and patronymic | gender by a vote over the words before every mention («позивачка», «сина», «громадянин») and the verb or relative pronoun after it («звернулася», «перебував», «, яка»); case from the cue before each mention («до», «з», «позивачу», «зобов'язати», a role word) |
| `АДРЕСА_n` | a row of an address table rendered in one of the styles of court decisions | the region and the settlements the decision names («… області», a court of the region, «м. Одеси», «с. Нерубайського») |
| `НОМЕР_n` | an identifier | the closest cue in the 45 characters before it, see the table below |
| `ІНФОРМАЦІЯ_n` | a date, an e-mail, a link, an account, a body, a name in quotes, … | 110 characters before and 70 after, see the sub-types below |

One placeholder index is one identity. The value is drawn at the first mention and rendered at every mention: a
person or a body in the case each mention needs, and an address sometimes with full words instead of abbreviations.

## НОМЕР sub-types

| sub-type | cue before the placeholder | example value |
|---|---|---|
| `rnokpp` | РНОКПП, ІПН, ідентифікаційний / податковий номер | `3192832764` |
| `passport` | паспорт, посвідчення, ID-картка | `КВ 123456`, `серії КВ № 123456`, `935030564 (УНЗР 19900101-01234)` |
| `svidotstvo` | свідоцтво, диплом, посвідчення водія, «серії» | `АВ 123456` |
| `iban` | рахунок, IBAN, р/р | `UA593282090000026978480184514` |
| `card` | банківська / платіжна картка | `4149 6090 1234 5678` |
| `phone` | тел., телефон, мобільний | `+38 (067) 123-45-67` |
| `imei` | IMEI | 15 digits |
| `vin` | VIN, кузов, шасі | 17 characters, without I, O or Q |
| `vehicle` | д.н.з., номерний знак, автомобіль | `АА 1234 ВС`, `KA1234XB` |
| `military` | військова частина, в/ч | `А1234` |
| `provadzhennia` | виконавче провадження, ВП №, АСВП | `67871331` |
| `generic` | none of the above | any of the above, or a serial-like code |

Where a placeholder appears several times, the last mention that has a cue decides.

## ІНФОРМАЦІЯ sub-types

The rules are tried in a fixed order. First come quotes around the placeholder, then the right-hand context, then
rules that must beat the general ones, then the general cues, and finally fallbacks with wider windows. Every mention
of a placeholder gets a sub-type. A majority vote over the mentions decides, and a mention that is not masked
outvotes a masked one.

| sub-type | value | hints | label or mask |
|---|---|---|---|
| `dob` | birth date | `child` (a minor), `no_roku` (the text continues with «року»), `style` | label |
| `death` | date of death; on or after 24.02.2022 after a cue of the war; after the birth date next to it | `weak` for a loose cue | label, mask when weak |
| `derived` | «до досягнення повноліття, тобто до …»: a child's generated birth date + 18 / 23 / 3 years | `until` | label |
| `date_event` | a recent date that is neither birth nor death | | mask |
| `email` | personal e-mail, usually built from the name of the last person mentioned | | label |
| `url` | a site, a page (article, video, post) or a profile of the network the text names | `url_kind` | label; mask after a video-conference cue |
| `nick` | an account handle or a page / channel link | `nick_kind` | mask |
| `ident` | a login or a system identifier | | mask |
| `military_name` | what follows «військова частина»: a code, a name in quotes or the formation | | label |
| `org` | a body, declined by its context | `org_kind`: `party`, `unit`, `short`, `holder`, `official` | label for a military body, mask otherwise |
| `quoted` | the bare name inside the quotes of the text | `quote_kind`: `formation`, `company`, `bank`, `institution`, `person`, `unknown` | label for a formation, mask otherwise |
| `place` | a settlement («уродженця …») in the region of the decision | | mask |
| `other` | no rule matched: an institution | | mask |

### Organisations

For an `org` slot, the kind of body depends on the slot and on what the decision is about. A decision is about the
military when it mentions military words. It is commercial when it is a commercial court's or the caller passes
`kind="ГПК"`. These are the shares (military / civil / company), measured on hand-labelled slots:

| slot | serviceman's case | commercial case | other |
|---|---|---|---|
| `party`: a party to the case («позовом до …», «зобов'язати …») | 95 / 4 / 1 | 5 / 15 / 80 | 70 / 25 / 5 |
| `holder`: a holder of records, a place of work or custody | 60 / 25 / 15 | 10 / 45 / 45 | 10 / 45 / 45 |

These slot kinds are fixed by the context:

- `unit`: the unit's own name, where its code stands in the open next to it.
- `short`: an abbreviation after «(далі - …)». It is built from the body before the bracket when there is one.
- `official`: the court, prosecutor's office or bank of an official. It is masked.

A name that already stands in the decision, or that was drawn for another placeholder of it, is drawn again (up to
5 times).

A body is declined as a phrase: the head noun and the adjectives before it follow the case, and the tail stays as it
is. For example, «Головне управління» + «Пенсійного фонду України в Одеській області» gives «Головному управлінню
Пенсійного фонду України в Одеській області». The case of each mention comes from the cue before it. A list of
placeholders or open names before the slot is skipped («позовом до ІНФОРМАЦІЯ_1, ІНФОРМАЦІЯ_2» puts both in the
genitive).

## Masks

A masked entity has a value, but the value's kind is uncertain or it is not personal data:

- `info_unsure`: the context does not tell what the register hid (the sub-types marked «mask» above).
- `info_civil_org`: a civil body, a company, a bank, a hospital, a school or a penal institution in a hidden slot. Such
  a name identifies no natural person, and most decisions name such bodies in the open, so a label there would
  contradict the rest of the corpus.

Every mention of a masked placeholder is masked. When you train a model, ignore these spans in the loss.

## Reproducibility

`Filler(seed)` draws everything from one `random.Random`. With `fill(text, doc_id=…)`, the stream is reseeded from
`"{seed}:{doc_id}"` (plus `":{version}"` for `version > 1`). The values of a document then depend only on the seed,
the id and the version.
