"""Embedded reference data and taxonomy/clause-bank loading for the synthetic generator.

The generator needs three kinds of outside-world knowledge that a language model
cannot be trusted to invent correctly: which names are common in Norway (so
generated people look like a population, not a model's favourite three names),
which postal code goes with which place (getting `0580 Bergen` instead of `0580
Oslo` teaches a wrong association), and which names belong to real public figures
(so a sampled name is never accidentally libellous). All three are embedded here
rather than fetched, because the generator must be reproducible offline and the
lists are small enough to vendor.

This module also owns loading the three contract files that parallel workstreams
are producing (`data/synthetic/taxonomy.json`, `types_config.yaml`,
`clause_bank.json`). Those files may not exist yet, so every loader falls back to
a built-in default that matches the contract shape described in
`docs/PROJECT_SPEC_V2.md` Section 2 (the 59-type, three-tier taxonomy). The
fallback is not a toy: it is the full 59-type table transcribed from the spec, so
the generator is usable end-to-end before the real files land, and swaps over
silently once they do.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Names. A few hundred first names and surnames drawn from general knowledge of
# SSB's common-name statistics: high-frequency Norwegian first names across
# generations (older cohorts skew Jan/Kari-style, younger skew Emma/Noah-style)
# and the most common patronymic-derived surnames (-sen forms dominate).
# ---------------------------------------------------------------------------

FIRST_NAMES_MALE: List[str] = [
    "Jan", "Per", "Ole", "Lars", "Erik", "Anders", "Kristian", "Morten", "Bjørn",
    "Geir", "Kjell", "Arne", "Svein", "Terje", "Trond", "Odd", "Rune", "Frode",
    "Tor", "Roy", "Kenneth", "Stian", "Thomas", "Andreas", "Martin", "Daniel",
    "Christian", "Fredrik", "Henrik", "Magnus", "Sander", "Kristoffer", "Jonas",
    "Markus", "Mathias", "Emil", "Oskar", "Elias", "Noah", "William", "Oliver",
    "Lucas", "Filip", "Aksel", "Isak", "Theodor", "Jakob", "Tobias", "Sebastian",
    "Håkon", "Vegard", "Espen", "Øyvind", "Ståle", "Ronny", "Roger", "Dag",
    "Knut", "Harald", "Helge", "Ivar", "Jarle", "Egil", "Leif", "Nils", "Ola",
    "Reidar", "Sigurd", "Sverre", "Torstein", "Gunnar", "Halvor", "Ingvar",
    "Jon", "Kåre", "Magne", "Oddvar", "Rolf", "Sigmund", "Steinar", "Trygve",
    "Vidar", "Yngve", "Bjarne", "Einar", "Finn", "Gustav", "Hans", "Ivan",
    "Johan", "Karl", "Ludvig", "Herman", "Georg", "Alf", "Asbjørn", "Bjarte",
    "Eivind", "Gaute", "Jostein", "Kristen", "Lasse", "Njål", "Oskar", "Pål",
    "Sondre", "Tarjei", "Ulrik", "Vetle", "Are", "Bård", "Dagfinn", "Erling",
    "Frank", "Gunder", "Halvard", "Iver", "Jens", "Kolbein", "Leiv", "Mons",
]

FIRST_NAMES_FEMALE: List[str] = [
    "Anne", "Kari", "Inger", "Liv", "Marit", "Randi", "Bjørg", "Solveig",
    "Astrid", "Gerd", "Aud", "Wenche", "Ellen", "Berit", "Turid", "Grethe",
    "Tone", "Hilde", "Kristin", "Anita", "Vibeke", "Elisabeth", "Camilla",
    "Silje", "Ida", "Emma", "Nora", "Sara", "Maja", "Ingrid", "Thea", "Emilie",
    "Sofie", "Julie", "Amalie", "Frida", "Tuva", "Live", "Selma", "Aurora",
    "Ella", "Mia", "Leah", "Hanna", "Vilde", "Marte", "Malin", "Linnea",
    "Sandra", "Monica", "Heidi", "Tove", "Bente", "Wenke", "Gunn", "Åse",
    "Solfrid", "Torhild", "Ragnhild", "Signe", "Sigrid", "Marianne", "Susanne",
    "Kristine", "Lene", "Trine", "Hege", "Merete", "Elin", "Karoline",
    "Rebecca", "Andrea", "Victoria", "Josefine", "Ingeborg", "Synnøve",
    "Åshild", "Gudrun", "Judith", "Borghild", "Dagny", "Eldbjørg", "Reidun",
    "Ruth", "Sonja", "Unni", "Vera", "Yngvild", "Agnes", "Beate", "Cathrine",
    "Dorthe", "Eva", "Gunhild", "Hanne", "Iren", "Jorunn", "Kirsten", "Laila",
    "Mette", "Nina", "Oda", "Pia", "Rita", "Solveig", "Tina", "Unn", "Wibeke",
    "Åsta", "Birgitte", "Charlotte", "Ester", "Gøril",
]

SURNAMES: List[str] = [
    "Hansen", "Johansen", "Olsen", "Larsen", "Andersen", "Pedersen", "Nilsen",
    "Kristiansen", "Jensen", "Karlsen", "Johnsen", "Pettersen", "Eriksen",
    "Berg", "Haugen", "Hagen", "Johannessen", "Andreassen", "Jacobsen", "Dahl",
    "Jørgensen", "Halvorsen", "Henriksen", "Lund", "Sørensen", "Jakobsen",
    "Moen", "Gundersen", "Iversen", "Strand", "Solberg", "Svendsen",
    "Martinsen", "Amundsen", "Fredriksen", "Paulsen", "Bakken", "Knutsen",
    "Danielsen", "Simonsen", "Vik", "Berge", "Ruud", "Rasmussen", "Solheim",
    "Aas", "Bø", "Braathen", "Kristoffersen", "Skaug", "Aasen", "Eide", "Foss",
    "Kvam", "Lie", "Moe", "Reppe", "Sæther", "Aune", "Bakke", "Berget",
    "Bjerke", "Brekke", "Brenna", "Dahle", "Edvardsen", "Eggen", "Engen",
    "Evensen", "Fjeld", "Gabrielsen", "Gran", "Gulbrandsen", "Haga",
    "Halvorsrud", "Haukland", "Helle", "Hermansen", "Holm", "Holmen",
    "Hovden", "Husby", "Isaksen", "Kolstad", "Kristensen", "Lorentzen",
    "Løvlie", "Mathisen", "Nygård", "Nyland", "Olsvik", "Osmundsen", "Ottesen",
    "Ramsøy", "Reiersen", "Ringstad", "Rognes", "Rudi", "Rørvik", "Sand",
    "Sandnes", "Sandvik", "Selvik", "Skogen", "Skøien", "Stenersen",
    "Stensrud", "Sundby", "Sundet", "Sæbø", "Teigen", "Thoresen", "Tveit",
    "Tveiten", "Ulriksen", "Vaage", "Valle", "Vangen", "Viken", "Vold", "Wold",
    "Ødegård", "Øien", "Østby", "Aaberg", "Tangen", "Rist", "Kalvøy", "Saga",
    "Skare", "Wig", "Nordahl", "Fjeldstad", "Rygg", "Skei", "Vatne", "Sørum",
    "Wangen", "Hoel", "Løken", "Melby", "Ness", "Opdahl", "Sætre",
]

# ---------------------------------------------------------------------------
# Real postal code / place pairings. Norway Post assigns a single place name to
# each 4-digit code; getting the pairing wrong (a real code with the wrong
# place) is worse than an obviously fake one, because it teaches a false
# association. This list favours codes we are confident of: city centres and
# well-known suburbs across the country's regions.
# ---------------------------------------------------------------------------

POSTAL_PAIRS: List[Tuple[str, str]] = [
    ("0010", "Oslo"), ("0050", "Oslo"), ("0101", "Oslo"), ("0150", "Oslo"),
    ("0170", "Oslo"), ("0250", "Oslo"), ("0301", "Oslo"), ("0370", "Oslo"),
    ("0450", "Oslo"), ("0550", "Oslo"), ("0650", "Oslo"), ("0658", "Oslo"),
    ("0750", "Oslo"), ("0850", "Oslo"), ("0950", "Oslo"), ("1051", "Oslo"),
    ("5003", "Bergen"), ("5006", "Bergen"), ("5010", "Bergen"),
    ("5015", "Bergen"), ("5020", "Bergen"), ("5034", "Bergen"),
    ("5040", "Bergen"), ("5057", "Bergen"), ("5063", "Bergen"),
    ("5081", "Bergen"), ("5096", "Bergen"),
    ("7010", "Trondheim"), ("7013", "Trondheim"), ("7018", "Trondheim"),
    ("7020", "Trondheim"), ("7030", "Trondheim"), ("7040", "Trondheim"),
    ("7050", "Trondheim"), ("7080", "Heimdal"),
    ("4001", "Stavanger"), ("4005", "Stavanger"), ("4008", "Stavanger"),
    ("4010", "Stavanger"), ("4020", "Stavanger"), ("4021", "Stavanger"),
    ("4032", "Stavanger"), ("4033", "Stavanger"),
    ("3003", "Drammen"), ("3010", "Drammen"), ("3015", "Drammen"),
    ("3020", "Drammen"), ("3025", "Drammen"), ("3040", "Drammen"),
    ("1601", "Fredrikstad"), ("1606", "Fredrikstad"), ("1607", "Fredrikstad"),
    ("1612", "Fredrikstad"),
    ("1501", "Moss"), ("1516", "Moss"), ("1517", "Moss"),
    ("1701", "Sarpsborg"), ("1706", "Sarpsborg"), ("1707", "Sarpsborg"),
    ("3101", "Tønsberg"), ("3111", "Tønsberg"), ("3117", "Tønsberg"),
    ("3701", "Skien"), ("3710", "Skien"), ("3719", "Skien"), ("3724", "Skien"),
    ("3901", "Porsgrunn"), ("3907", "Porsgrunn"), ("3912", "Porsgrunn"),
    ("4602", "Kristiansand"), ("4610", "Kristiansand"),
    ("4616", "Kristiansand"), ("4621", "Kristiansand"),
    ("4630", "Kristiansand"),
    ("6001", "Ålesund"), ("6002", "Ålesund"), ("6005", "Ålesund"),
    ("6010", "Ålesund"), ("6017", "Ålesund"),
    ("6100", "Volda"), ("6150", "Ørsta"),
    ("6501", "Kristiansund"), ("6509", "Kristiansund"),
    ("6510", "Kristiansund"),
    ("6800", "Førde"),
    ("8001", "Bodø"), ("8003", "Bodø"), ("8005", "Bodø"), ("8006", "Bodø"),
    ("8009", "Bodø"),
    ("9008", "Tromsø"), ("9010", "Tromsø"), ("9011", "Tromsø"),
    ("9016", "Tromsø"),
    ("9500", "Alta"), ("9600", "Hammerfest"), ("9700", "Lakselv"),
    ("9750", "Honningsvåg"),
    ("2001", "Lillestrøm"), ("2003", "Lillestrøm"), ("2007", "Kjeller"),
    ("2010", "Strømmen"), ("2013", "Skjetten"), ("2016", "Frogner"),
    ("2020", "Skedsmokorset"),
    ("2317", "Hamar"), ("2318", "Hamar"), ("2321", "Hamar"),
    ("2609", "Lillehammer"), ("2615", "Lillehammer"), ("2618", "Lillehammer"),
    ("2624", "Lillehammer"),
    ("2801", "Gjøvik"), ("2815", "Gjøvik"), ("2816", "Gjøvik"),
    ("7600", "Levanger"), ("7700", "Steinkjer"),
    ("8656", "Mosjøen"), ("8800", "Sandnessjøen"),
    ("9300", "Finnsnes"), ("9900", "Kirkenes"),
    ("1400", "Ski"), ("1430", "Ås"), ("1440", "Drøbak"),
    ("1450", "Nesoddtangen"), ("1470", "Lørenskog"), ("1472", "Fjellhamar"),
    ("1476", "Rasta"), ("1481", "Hagan"),
    ("1350", "Lommedalen"), ("1351", "Rud"), ("1360", "Fornebu"),
    ("1363", "Høvik"), ("1366", "Lysaker"), ("1367", "Snarøya"),
    ("1369", "Stabekk"), ("1383", "Asker"), ("1394", "Nesbru"),
    ("1396", "Billingstad"),
    ("3400", "Lier"), ("3300", "Hokksund"), ("3611", "Kongsberg"),
    ("3616", "Kongsberg"), ("3626", "Rollag"),
    ("4306", "Sandnes"), ("4319", "Sandnes"), ("4325", "Sandnes"),
    ("5501", "Haugesund"), ("5527", "Haugesund"),
    ("7900", "Rørvik"), ("7970", "Kolvereid"),
    ("8450", "Stokmarknes"), ("8300", "Svolvær"), ("8480", "Andenes"),
]

STREET_NAMES: List[str] = [
    "Fjellveien", "Skogveien", "Kirkegata", "Storgata", "Skolegata",
    "Parkveien", "Industriveien", "Strandveien", "Elveveien", "Bjørkelunden",
    "Granveien", "Solbakken", "Bakkegata", "Hovedgata", "Lillegata",
    "Nedre Torggate", "Øvre Torggate", "Ringveien", "Furuveien", "Lyngveien",
    "Bergveien", "Åsveien", "Myrveien", "Dalveien", "Havnegata", "Torvet",
    "Nygata", "Kongensgate", "Bispegata", "Domkirkeplassen",
]

# ---------------------------------------------------------------------------
# Real Norwegian public figures, embedded so a generated name can be checked
# against it (G3). Politicians, royals, athletes and media personalities --
# anyone whose full name attached to invented crimes, illness or sexual
# orientation would be a real-world harm, which is the one failure mode in
# this project with consequences outside it.
# ---------------------------------------------------------------------------

PUBLIC_FIGURES: List[str] = [
    "Jonas Gahr Støre", "Erna Solberg", "Trygve Slagsvold Vedum",
    "Siv Jensen", "Sylvi Listhaug", "Audun Lysbakken", "Une Bastholm",
    "Kjell Ingolf Ropstad", "Bjørnar Moxnes", "Knut Arild Hareide",
    "Jens Stoltenberg", "Kristin Halvorsen", "Carl Hagen",
    "Ine Eriksen Søreide", "Anniken Huitfeldt", "Espen Barth Eide",
    "Jan Tore Sanner", "Torbjørn Røe Isaksen", "Terje Søviknes",
    "Ketil Solvik-Olsen", "Guri Melby", "Marit Arnstad",
    "Liv Signe Navarsete", "Per Sandberg", "Hadia Tajik",
    "Raymond Johansen", "Marianne Marthinsen", "Tonje Brenna",
    "Jan Christian Vestre", "Emilie Enger Mehl", "Vidar Helgesen",
    "Kjersti Toppe", "Ola Borten Moe", "Anette Trettebergstuen",
    "Harald Femte", "Kong Harald", "Dronning Sonja", "Kronprins Haakon",
    "Kronprinsesse Mette-Marit", "Prinsesse Ingrid Alexandra",
    "Prins Sverre Magnus", "Prinsesse Märtha Louise", "Prinsesse Astrid",
    "Magnus Carlsen", "Martin Ødegaard", "Erling Haaland", "Casper Ruud",
    "Karsten Warholm", "Marit Bjørgen", "Therese Johaug", "Petter Northug",
    "Ole Einar Bjørndalen", "Johannes Thingnes Bø", "Kjetil Jansrud",
    "Aksel Lund Svindal", "Henrik Kristoffersen", "Ada Hegerberg",
    "Caroline Graham Hansen", "Jakob Ingebrigtsen", "Filip Ingebrigtsen",
    "Henrik Ingebrigtsen", "Sondre Norstad Moen", "Isabell Herlovsen",
    "Ronny Deila", "Ole Gunnar Solskjær", "John Arne Riise",
    "Tore André Flo", "Morten Gamst Pedersen", "Solveig Gulbrandsen",
    "Fredrik Skavlan", "Anne Lindmo", "Stian Barsnes Simonsen",
    "Else Kåss Furuseth", "Kristian Valen", "Sigrid Bonde Tusvik",
    "Lene Alexandra Øien", "Anne-Kat Hærland", "Kjersti Flaa", "Tore Sagen",
    "Thomas Numme", "Harald Eia", "Bård Tufte Johansen",
    "Vegard Ylvisåker", "Bjarte Tjøstheim", "Jo Nesbø",
    "Karl Ove Knausgård", "Maja Lunde", "Jostein Gaarder",
    "Erik Solheim", "Kristin Clemet", "Erling Lae", "Fabian Stang",
    "Marianne Borgen", "Rune Bakervik", "Alfred Bjørlo",
    "Ingrid Fiskaa", "Lan Marie Berg", "Sirin Stav", "Sofie Marhaug",
    "Rasmus Hansson", "Geir Jørgen Bekkevold", "Olaug Bollestad",
    "Dag Terje Andersen", "Masud Gharahkhani", "Nikolai Astrup",
    "Tina Bru", "Henrik Asheim", "Erlend Wiborg", "Gjermund Hagesæter",
    "Christian Tybring-Gjedde", "Morten Wold", "Bård Hoksrud",
    "Solveig Horne", "Silje Hjemdal", "Jon Engen-Helgheim",
    "Roy Steffensen", "Helge André Njåstad", "Erik Skutle",
    "Peter Frølich", "Mudassar Kapur", "Heidi Nordby Lunde",
    "Michael Tetzschner", "Svein Harberg", "Ingjerd Schou",
    "Margret Hagerup", "Turid Kristensen", "Aleksander Stokkebø",
    "Åsmund Aukrust", "Jonas Gahr", "Torstein Tvedt Solberg",
    "Cecilie Myrseth", "Even Eriksen", "Sverre Myrli",
    "Kirsti Leirtrø", "Lene Vågslid", "Maria Aasen-Svensrud",
    "Petter Eide", "Kathy Lie", "Grete Wold", "Kari Elisabeth Kaski",
    "Freddy André Øvstegård", "Ingrid Alexandra Fadnes",
    "Bjørn Arild Gram", "Sigbjørn Gjelsvik", "Geir Pollestad",
    "Sandra Borch", "Anne Beathe Tvinnereim", "Willfred Nordlund",
    "Marit Knutsdatter Strand", "Ole André Myhrvold",
    "Nils Kristen Sandtrøen", "Anette Trettebergstuen",
    "Ingvild Kjerkol", "Jan Bøhler", "Lubna Jaffery",
]

AGENCY_NAMES: List[str] = [
    "Mattilsynet", "NAV", "Politiet", "UDI", "Skatteetaten", "Husbanken",
    "Barnevernet", "IMDi", "Statsforvalteren", "Fylkesmannen", "Kripos",
    "Politidirektoratet", "Arbeidstilsynet", "Skattedirektoratet",
    "Tolletaten", "Utlendingsdirektoratet", "Utlendingsnemnda",
    "Helsedirektoratet", "Statens vegvesen", "Brønnøysundregistrene",
    "Domstolene", "Tingretten", "Lagmannsretten", "Høyesterett",
    "Fastlegekontoret", "Legevakten", "Sykehuset", "Kommunen",
    "Bydelen", "Politidistriktet", "Namsfogden", "Konfliktrådet",
    "Datatilsynet", "Forbrukertilsynet", "Kriminalomsorgen",
    "Statens innkrevingssentral", "Trygdeetaten", "Folkeregisteret",
]

# ---------------------------------------------------------------------------
# The 59-type taxonomy fallback (PROJECT_SPEC_V2.md Section 2), used whenever
# data/synthetic/taxonomy.json has not been produced yet. Kept in sync with
# the spec table by construction: tier, GDPR flag, legacy 16-type mapping and
# whether the type's value is a discrete "value" or a narrative "clause".
# ---------------------------------------------------------------------------

_TIER_A = [
    "BANK_ACCOUNT", "CASE_NUMBER", "CREDIT_CARD", "CRYPTO", "DATE_OF_BIRTH",
    "DEVICE_ID", "DRIVER_LICENSE", "EMAIL", "FAX_NUMBER", "IBAN",
    "IDENTITY_CARD", "INSURANCE_NUMBER", "IP_ADDRESS", "LICENSE_PLATE",
    "MEDICAL_LICENSE", "MILITARY_ID", "NATIONAL_ID", "ORG_NUMBER",
    "PASSPORT", "PASSWORD", "PHONE", "POSTAL_CODE", "SOCIAL_MEDIA",
    "STUDENT_ID", "TAX_ID", "URL", "USERNAME", "VISA_NUMBER",
]

_TIER_B_VALUE = [
    "ADDRESS", "AGE", "ANIMAL_INFO", "DATE_TIME", "GENDER", "LOCATION",
    "MARITAL_STATUS", "NATIONALITY", "ORGANIZATION", "PERSON",
]
_TIER_B_CLAUSE = ["ACADEMIC_RECORD", "EMPLOYMENT", "FAMILY_RELATION"]

# Matches the real data/synthetic/taxonomy.json: 20 clause-kind types, of which
# IDENTIFIABLE_IMAGE is the one Tier C type that turned out to be "value" kind
# rather than "clause" -- a short descriptive phrase, not a judgement clause.
_TIER_C_CLAUSE = [
    "AGE_INFO", "BEHAVIORAL_PATTERN", "BIOMETRIC_DATA", "CONTEXT_SENSITIVE",
    "CRIMINAL", "DISABILITY", "ECONOMIC_STATUS", "ETHNICITY", "FINANCIAL",
    "GENETIC_DATA", "HEALTH", "IMMIGRATION_STATUS", "MEDICATION",
    "POLITICAL", "RELIGIOUS_BELIEF", "SEXUAL_ORIENTATION", "TRADE_UNION",
]
_TIER_C_VALUE = ["IDENTIFIABLE_IMAGE"]

_GDPR_ART9 = {
    "BIOMETRIC_DATA": "Art. 9 -- biometric data",
    "DISABILITY": "Art. 9 -- health",
    "ETHNICITY": "Art. 9 -- racial or ethnic origin",
    "GENETIC_DATA": "Art. 9 -- genetic data",
    "HEALTH": "Art. 9 -- health",
    "MEDICATION": "Art. 9 -- health",
    "POLITICAL": "Art. 9 -- political opinions",
    "RELIGIOUS_BELIEF": "Art. 9 -- religious or philosophical beliefs",
    "SEXUAL_ORIENTATION": "Art. 9 -- sex life / sexual orientation",
    "TRADE_UNION": "Art. 9 -- trade union membership",
    "CRIMINAL": "Art. 10 -- criminal convictions and offences",
}

_LEGACY_MAP = {
    "PERSON": "PERSON", "DATE_TIME": "DATE_TIME", "HEALTH": "HEALTH_INFO",
    "NATIONAL_ID": "GOV_ID", "ADDRESS": "NO_ADDRESS", "CRIMINAL": "CRIMINAL_RECORD",
    "POSTAL_CODE": "POSTAL_CODE", "PHONE": "NO_PHONE_NUMBER",
    "EMAIL": "EMAIL_ADDRESS", "FAMILY_RELATION": "FAMILY_RELATION",
    "FINANCIAL": "FINANCIAL_INFO", "EMPLOYMENT": "EMPLOYMENT_INFO",
    "POLITICAL": "POLITICAL_CASE", "BEHAVIORAL_PATTERN": "BEHAVIORAL_PATTERN",
    "ECONOMIC_STATUS": "ECONOMIC_STATUS", "SEXUAL_ORIENTATION": "SEXUAL_ORIENTATION",
    "LICENSE_PLATE": "GOV_ID",
}


def _default_taxonomy() -> dict:
    """Build the embedded 59-type taxonomy matching PROJECT_SPEC_V2.md Section 2."""
    types = []
    for name in _TIER_A:
        types.append({
            "name": name, "tier": "A", "gdpr": _GDPR_ART9.get(name),
            "legacy_type": _LEGACY_MAP.get(name), "value_kind": "value",
            "definition": f"Tier A mechanical identifier: {name.replace('_', ' ').lower()}.",
        })
    for name in _TIER_B_VALUE:
        types.append({
            "name": name, "tier": "B", "gdpr": _GDPR_ART9.get(name),
            "legacy_type": _LEGACY_MAP.get(name), "value_kind": "value",
            "definition": f"Tier B contextual attribute: {name.replace('_', ' ').lower()}.",
        })
    for name in _TIER_B_CLAUSE:
        types.append({
            "name": name, "tier": "B", "gdpr": _GDPR_ART9.get(name),
            "legacy_type": _LEGACY_MAP.get(name), "value_kind": "clause",
            "definition": f"Tier B contextual narrative: {name.replace('_', ' ').lower()}.",
        })
    for name in _TIER_C_CLAUSE:
        types.append({
            "name": name, "tier": "C", "gdpr": _GDPR_ART9.get(name),
            "legacy_type": _LEGACY_MAP.get(name), "value_kind": "clause",
            "definition": f"Tier C judgement clause: {name.replace('_', ' ').lower()}.",
        })
    for name in _TIER_C_VALUE:
        types.append({
            "name": name, "tier": "C", "gdpr": _GDPR_ART9.get(name),
            "legacy_type": _LEGACY_MAP.get(name), "value_kind": "value",
            "definition": f"Tier C descriptive value: {name.replace('_', ' ').lower()}.",
        })
    return {"types": types, "legacy_map": _LEGACY_MAP}


def load_taxonomy(path: Optional[str]) -> dict:
    """Load the type taxonomy, falling back to the embedded 59-type default.

    Args:
        path: Path to `taxonomy.json`, or None/missing to use the fallback.

    Returns:
        Dict with `types` (list of type records) and `legacy_map`.
    """
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    return _default_taxonomy()


def taxonomy_index(taxonomy: dict) -> Dict[str, dict]:
    """Return the taxonomy's types indexed by name."""
    return {t["name"]: t for t in taxonomy["types"]}


def write_types_config_yaml(taxonomy: dict, path: str) -> None:
    """Write a `types_config.yaml` that `tools/validate_labels.py --config` can read.

    Used when the real `data/synthetic/types_config.yaml` has not been produced
    yet by the parallel workstream that owns it; synthesized from whichever
    taxonomy (real or fallback) is currently loaded, so G1 always has a config
    consistent with the types actually used to label documents.

    Args:
        taxonomy: Taxonomy dict as returned by `load_taxonomy`.
        path: Output path for the generated YAML file.
    """
    lines = ["entity_types:"]
    for entry in taxonomy["types"]:
        definition = entry.get("definition", "").replace('"', "'")
        lines.append(f'  {entry["name"]}: "{definition}"')
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


_DEFAULT_CLAUSE_BANK = {
    "EMPLOYMENT": [
        {"text": "arbeider som butikkmedarbeider hos lokal dagligvarebutikk", "form": "nb", "subject": "employment", "difficulty": "easy"},
        {"text": "har vore tilsett som lærar ved skulen i over ti år", "form": "nn", "subject": "employment", "difficulty": "medium"},
        {"text": "mistet jobben sin som følge av nedbemanning i bedriften", "form": "nb", "subject": "employment", "difficulty": "medium"},
    ],
    "FAMILY_RELATION": [
        {"text": "er gift og har to barn sammen med ektefellen", "form": "nb", "subject": "family", "difficulty": "easy"},
        {"text": "bur saman med sambuaren og eit fellesbarn", "form": "nn", "subject": "family", "difficulty": "easy"},
    ],
    "ACADEMIC_RECORD": [
        {"text": "fullførte bachelorgrad i sykepleie med gode karakterer", "form": "nb", "subject": "academic", "difficulty": "medium"},
        {"text": "har vore skulke frå vidaregåande skule fleire gonger", "form": "nn", "subject": "academic", "difficulty": "medium"},
    ],
    "ANIMAL_INFO": [
        {"text": "eier tre hunder som holdes i dårlig forfatning", "form": "nb", "subject": "animal", "difficulty": "medium"},
    ],
    "AGE_INFO": [
        {"text": "er mindreårig og krever særskilt oppfølging fra verge", "form": "nb", "subject": "vulnerability", "difficulty": "medium"},
    ],
    "BEHAVIORAL_PATTERN": [
        {"text": "viser gjentatt aggressiv atferd overfor naboer", "form": "nb", "subject": "behaviour", "difficulty": "hard"},
        {"text": "har vist teikn på isolasjon og tilbaketrekking den siste tida", "form": "nn", "subject": "behaviour", "difficulty": "hard"},
    ],
    "BIOMETRIC_DATA": [
        {"text": "fingeravtrykk registrert i forbindelse med saken", "form": "nb", "subject": "biometric", "difficulty": "medium"},
    ],
    "CONTEXT_SENSITIVE": [
        {"text": "opplyser om forhold som kan ha betydning for saken, men som ikke er nærmere spesifisert", "form": "nb", "subject": "context", "difficulty": "hard"},
    ],
    "CRIMINAL": [
        {"text": "ble domfelt for skadeverk i 2019, sonet samfunnsstraff", "form": "nb", "subject": "criminal", "difficulty": "hard"},
        {"text": "vart sikta for grovt tjuveri, saka vart seinare lagt bort", "form": "nn", "subject": "criminal", "difficulty": "hard"},
    ],
    "DISABILITY": [
        {"text": "har en fysisk funksjonsnedsettelse som krever tilrettelegging", "form": "nb", "subject": "disability", "difficulty": "medium"},
    ],
    "ECONOMIC_STATUS": [
        {"text": "har betydelig gjeld og mottar økonomisk sosialhjelp", "form": "nb", "subject": "economic", "difficulty": "hard"},
        {"text": "har god økonomi og eig bustad utan gjeld", "form": "nn", "subject": "economic", "difficulty": "medium"},
    ],
    "ETHNICITY": [
        {"text": "identifiserer seg som same og er registrert i valmanntalet for Sametinget", "form": "nb", "subject": "ethnicity", "difficulty": "hard"},
    ],
    "FINANCIAL": [
        {"text": "har en årsinntekt godt over gjennomsnittet", "form": "nb", "subject": "financial", "difficulty": "medium"},
    ],
    "GENETIC_DATA": [
        {"text": "har tatt en genetisk test som viser arvelig disposisjon for hjertesykdom", "form": "nb", "subject": "genetic", "difficulty": "hard"},
    ],
    "HEALTH": [
        {"text": "lider av type 2 diabetes og kronisk depresjon", "form": "nb", "subject": "health", "difficulty": "hard"},
        {"text": "har vore sjukmeldt grunna alvorleg angstliding", "form": "nn", "subject": "health", "difficulty": "hard"},
    ],
    "IDENTIFIABLE_IMAGE": [
        {"text": "er avbildet i overvåkningsopptak fra hendelsen", "form": "nb", "subject": "image", "difficulty": "medium"},
    ],
    "IMMIGRATION_STATUS": [
        {"text": "har midlertidig oppholdstillatelse på humanitært grunnlag", "form": "nb", "subject": "immigration", "difficulty": "medium"},
    ],
    "MEDICATION": [
        {"text": "bruker fast Sertralin mot angst og depresjon", "form": "nb", "subject": "medication", "difficulty": "medium"},
    ],
    "POLITICAL": [
        {"text": "er aktivt medlem av Rødt og har stilt til kommunevalg", "form": "nb", "subject": "political", "difficulty": "hard"},
    ],
    "RELIGIOUS_BELIEF": [
        {"text": "er praktiserende medlem av Jehovas Vitner", "form": "nb", "subject": "religion", "difficulty": "hard"},
        {"text": "praktiserer islam og deltek jamleg i fredagsbøn", "form": "nn", "subject": "religion", "difficulty": "hard"},
    ],
    "SEXUAL_ORIENTATION": [
        {"text": "identifiserer seg som homofil og er åpen om dette overfor familien", "form": "nb", "subject": "orientation", "difficulty": "hard"},
    ],
    "TRADE_UNION": [
        {"text": "er tillitsvalgt i Fagforbundet på arbeidsplassen", "form": "nb", "subject": "union", "difficulty": "medium"},
    ],
    "negatives": {
        "HEALTH": ["Hunden bjeffer utrøstelig i mange timer"],
        "BEHAVIORAL_PATTERN": ["jobber lange skift og virker stresset"],
    },
}


def load_clause_bank(path: Optional[str]) -> dict:
    """Load the clause bank, falling back to a small embedded default.

    The real `data/synthetic/clause_bank.json` nests its per-type entries under
    a `clause_bank` key (`{"version": 2, "clause_bank": {TYPE: [...]}, "negatives":
    {...}}`) rather than putting `{TYPE: [...]}` at the top level the way the
    embedded default and this module's earlier draft contract did. This
    normalises either shape to the flat `{TYPE: [...], "negatives": {...}}`
    form every caller in this package expects, so callers never need to know
    which shape was on disk.

    Args:
        path: Path to `clause_bank.json`, or None/missing to use the fallback.

    Returns:
        Dict of `{TYPE: [clause entries]}` plus a `negatives` key.
    """
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        if "clause_bank" in raw:
            flat = dict(raw["clause_bank"])
            flat["negatives"] = raw.get("negatives", {})
            return flat
        return raw
    return _DEFAULT_CLAUSE_BANK


