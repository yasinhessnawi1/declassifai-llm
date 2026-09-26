"""Screening prompts for model-selection (docs/MODEL_SELECTION.md).

Each prompt gives the candidate LLM a structured, JSON-ish record of values that
must appear VERBATIM in the generated Norwegian public-sector document, plus 2-4
judgement clauses (health/criminal/economic/employment/political content) that
either must also appear verbatim ("seeded clause" prompts) or must be wrapped in
inline markers the model itself inserts ("marked generation" prompts, marked=True).

`values`: dict of label -> exact string that must be found as a substring of the
output (case-sensitive, per SYNTHETIC_DATA_SPEC.md's verbatim-inclusion gate).
`clauses`: list of judgement-clause strings. For non-marked prompts these are also
checked as verbatim substrings. For marked prompts, the check instead looks for a
marker pair of the form ⟦TYPE: ...⟦ around whatever clause the model wrote.
"""

MARK_OPEN = "⟦"

PROMPTS = [
    {
        "id": "P01_gp_referral_nb",
        "genre": "GP referral (henvisning)",
        "lang": "nb",
        "marked": False,
        "values": {
            "patient_name": "Kari Andersen Solheim",
            "fnr": "03057512345",
            "address": "Fjellveien 12B",
            "postal": "0580 Oslo",
            "phone": "+47 91234567",
            "date": "14.03.2026",
            "gp_org_number": "918234567",
        },
        "clauses": [
            "har diagnosen bipolar lidelse type II",
            "bruker for tiden lamotrigin 200 mg daglig",
        ],
        "instruction": (
            "Du er fastlege og skal skrive en henvisning til distriktspsykiatrisk senter (DPS) "
            "på bokmål. Bruk et strukturert henvisningsskjema med feltoverskrifter "
            "(Pasient, Fødselsnummer, Adresse, Telefon, Dato, Fastlegens org.nr, Henvisningsgrunn, "
            "Anamnese, Konklusjon).\n\n"
            "Bruk NØYAKTIG disse verdiene, ordrett, uten a endre stavemåte eller format:\n"
            "- Pasientens fulle navn: Kari Andersen Solheim\n"
            "- Fødselsnummer: 03057512345\n"
            "- Adresse: Fjellveien 12B\n"
            "- Postnummer og sted: 0580 Oslo\n"
            "- Telefon: +47 91234567\n"
            "- Dato: 14.03.2026\n"
            "- Fastlegekontorets organisasjonsnummer: 918234567\n\n"
            "I løpetekst/anamnese skal folgende to setninger sta verbatim, ordrett, uten omskrivning:\n"
            "1. \"har diagnosen bipolar lidelse type II\"\n"
            "2. \"bruker for tiden lamotrigin 200 mg daglig\"\n\n"
            "Skriv ca. 250-400 ord. Ikke bruk engelsk. Ikke bruk plassholdere som [navn] eller "
            "XXX - alle felt skal fylles ut med verdiene over."
        ),
    },
    {
        "id": "P02_police_report_nb",
        "genre": "police report (anmeldelse)",
        "lang": "nb",
        "marked": False,
        "values": {
            "suspect_name": "Jonas Brekke Haugland",
            "fnr": "16086234891",
            "address": "Kirkegata 45",
            "postal": "5003 Bergen",
            "case_number": "2026/00312-4",
            "date": "22.01.2026",
            "officer": "politibetjent Nina Fjeldstad",
        },
        "clauses": [
            "ble domfelt for grov kroppskrenkelse i 2019",
            "hadde en promille på 1,4 på gjerningstidspunktet",
        ],
        "instruction": (
            "Du er politibetjent og skal skrive en anmeldelsesrapport (politirapport) på bokmål, "
            "som løpende prosatekst med tydelige avsnitt (Innledning, Hendelsesforløp, Tidligere "
            "forhold, Konklusjon).\n\n"
            "Bruk NØYAKTIG disse verdiene, ordrett:\n"
            "- Mistenktes fulle navn: Jonas Brekke Haugland\n"
            "- Fødselsnummer: 16086234891\n"
            "- Adresse: Kirkegata 45\n"
            "- Postnummer og sted: 5003 Bergen\n"
            "- Saksnummer: 2026/00312-4\n"
            "- Dato: 22.01.2026\n"
            "- Rapportførende tjenestemann: politibetjent Nina Fjeldstad\n\n"
            "I teksten om tidligere forhold skal folgende to setninger sta verbatim, ordrett:\n"
            "1. \"ble domfelt for grov kroppskrenkelse i 2019\"\n"
            "2. \"hadde en promille på 1,4 på gjerningstidspunktet\"\n\n"
            "Skriv ca. 300-450 ord, formelt politispråk. Ingen engelsk, ingen plassholdere."
        ),
    },
    {
        "id": "P03_nav_decision_nb",
        "genre": "NAV benefit decision (vedtak)",
        "lang": "nb",
        "marked": False,
        "values": {
            "recipient_name": "Trude Eline Berg",
            "fnr": "27049045678",
            "address": "Storgata 8",
            "postal": "7013 Trondheim",
            "case_number": "NAV-2026-88213",
            "date": "05.02.2026",
            "caseworker": "saksbehandler Per Ove Lien",
        },
        "clauses": [
            "har en samlet gjeld på over 480 000 kroner",
            "mottar for tiden supplerende sosialhjelp fra kommunen",
        ],
        "instruction": (
            "Du skriver et NAV-vedtaksbrev på bokmål om avslag på arbeidsavklaringspenger. Bruk "
            "brevformat med feltoverskrifter (Til, Fødselsnummer, Adresse, Saksnummer, Dato, "
            "Saksbehandler) etterfulgt av løpende vedtakstekst med begrunnelse og klageadgang.\n\n"
            "Bruk NØYAKTIG disse verdiene, ordrett:\n"
            "- Navn: Trude Eline Berg\n"
            "- Fødselsnummer: 27049045678\n"
            "- Adresse: Storgata 8\n"
            "- Postnummer og sted: 7013 Trondheim\n"
            "- Saksnummer: NAV-2026-88213\n"
            "- Dato: 05.02.2026\n"
            "- Saksbehandler: saksbehandler Per Ove Lien\n\n"
            "I begrunnelsen skal folgende to setninger sta verbatim, ordrett:\n"
            "1. \"har en samlet gjeld på over 480 000 kroner\"\n"
            "2. \"mottar for tiden supplerende sosialhjelp fra kommunen\"\n\n"
            "Skriv ca. 300-400 ord, formelt forvaltningsspråk. Ingen engelsk, ingen plassholdere."
        ),
    },
    {
        "id": "P04_dismissal_hr_nb",
        "genre": "dismissal letter / HR grievance",
        "lang": "nb",
        "marked": False,
        "values": {
            "employee_name": "Anders Kvamme Lie",
            "org_number": "987654321",
            "employer": "Nordsjo Logistikk AS",
            "address": "Havnegata 3",
            "postal": "4014 Stavanger",
            "date": "10.04.2026",
            "hr_contact": "HR-rådgiver Mona Skeie",
        },
        "clauses": [
            "er tillitsvalgt i Fagforbundet",
            "har vært sykmeldt sammenhengende i 14 uker",
        ],
        "instruction": (
            "Du skriver et oppsigelsesbrev fra arbeidsgiver til ansatt på bokmål, inkludert en "
            "kort begrunnelse og informasjon om drofting med tillitsvalgt. Bruk brevformat med "
            "avsender, mottaker, dato og overskrift.\n\n"
            "Bruk NØYAKTIG disse verdiene, ordrett:\n"
            "- Ansattes navn: Anders Kvamme Lie\n"
            "- Arbeidsgivers organisasjonsnummer: 987654321\n"
            "- Arbeidsgiver: Nordsjo Logistikk AS\n"
            "- Adresse: Havnegata 3\n"
            "- Postnummer og sted: 4014 Stavanger\n"
            "- Dato: 10.04.2026\n"
            "- HR-kontakt: HR-rådgiver Mona Skeie\n\n"
            "I brodteksten skal folgende to setninger sta verbatim, ordrett:\n"
            "1. \"er tillitsvalgt i Fagforbundet\"\n"
            "2. \"har vært sykmeldt sammenhengende i 14 uker\"\n\n"
            "Skriv ca. 250-350 ord, formelt brevspråk. Ingen engelsk, ingen plassholdere."
        ),
    },
    {
        "id": "P05_udi_decision_nn",
        "genre": "UDI residence-permit decision",
        "lang": "nn",
        "marked": False,
        "values": {
            "applicant_name": "Amina Yusuf Ali",
            "case_number": "UDI-2026-55214",
            "birth_date": "12.11.1994",
            "address": "Bjorkeveien 2",
            "postal": "9008 Tromsø",
            "date": "18.02.2026",
            "caseworker": "sakshandsamar Ingrid Moe",
        },
        "clauses": [
            "har status som overforingsflyktning fra UNHCR",
            "er registrert med aktiv arbeidskontrakt hos Nord-Norsk Fiskeindustri AS",
        ],
        "instruction": (
            "Du skriv eit vedtaksbrev fra UDI om opphaldsløyve, på NYNORSK. Bruk brevformat med "
            "feltoverskrifter (Til, Saksnummer, Fødselsdato, Adresse, Dato, Sakshandsamar) og "
            "deretter ei grunngjeving strukturert som nummererte punkt.\n\n"
            "Bruk NØYAKTIG desse verdiane, ordrett:\n"
            "- Namn: Amina Yusuf Ali\n"
            "- Saksnummer: UDI-2026-55214\n"
            "- Fødselsdato: 12.11.1994\n"
            "- Adresse: Bjorkeveien 2\n"
            "- Postnummer og stad: 9008 Tromsø\n"
            "- Dato: 18.02.2026\n"
            "- Sakshandsamar: sakshandsamar Ingrid Moe\n\n"
            "I grunngjevinga skal desse to setningane sta verbatim, ordrett, IKKJE omsette til bokmål:\n"
            "1. \"har status som overforingsflyktning fra UNHCR\"\n"
            "2. \"er registrert med aktiv arbeidskontrakt hos Nord-Norsk Fiskeindustri AS\"\n\n"
            "Skriv heile brevet på nynorsk, ca. 300-400 ord. Ingen engelsk, ingen plasshaldarar, "
            "og bland ikkje inn bokmålsformer."
        ),
    },
    {
        "id": "P06_barnevern_nn",
        "genre": "barnevern concern report (bekymringsmelding)",
        "lang": "nn",
        "marked": False,
        "values": {
            "child_name": "Emma Fossheim",
            "child_birth": "04.09.2018",
            "parent_name": "Silje Fossheim",
            "address": "Skuleveien 9",
            "postal": "6812 Førde",
            "date": "01.03.2026",
            "reporter": "barnehagelærar Ola Vik",
        },
        "clauses": [
            "kjem ofte svolten og uvaska til barnehagen",
            "mor har opplyst om eige rusmisbruk i samtale",
        ],
        "instruction": (
            "Du skriv ei bekymringsmelding til barnevernstenesta fra ein barnehage, på NYNORSK. "
            "Bruk skjemaformat med feltoverskrifter (Barn, Fødselsdato, Foresatt, Adresse, Dato, "
            "Meldar) og deretter ei kort narrativ skildring av bekymringa.\n\n"
            "Bruk NØYAKTIG desse verdiane, ordrett:\n"
            "- Barnets namn: Emma Fossheim\n"
            "- Fødselsdato: 04.09.2018\n"
            "- Foresatt: Silje Fossheim\n"
            "- Adresse: Skuleveien 9\n"
            "- Postnummer og stad: 6812 Førde\n"
            "- Dato: 01.03.2026\n"
            "- Meldar: barnehagelærar Ola Vik\n\n"
            "I skildringa skal desse to setningane sta verbatim, ordrett, IKKJE omsette til bokmål:\n"
            "1. \"kjem ofte svolten og uvaska til barnehagen\"\n"
            "2. \"mor har opplyst om eige rusmisbruk i samtale\"\n\n"
            "Skriv heile meldinga på nynorsk, ca. 250-350 ord. Ingen engelsk, ingen plasshaldarar."
        ),
    },
    {
        "id": "P07_inkasso_nb",
        "genre": "tax / inkasso letter",
        "lang": "nb",
        "marked": False,
        "values": {
            "debtor_name": "Rune Fagerheim Dahl",
            "fnr": "09027834521",
            "address": "Lundveien 21",
            "postal": "3050 Mjøndalen",
            "case_number": "INK-2026-771402",
            "amount": "62 450 kroner",
            "date": "27.03.2026",
        },
        "clauses": [
            "har inngatt en nedbetalingsavtale som misligholdes for andre gang",
            "er registrert med betalingsanmerkning hos tre andre kreditorer",
        ],
        "instruction": (
            "Du skriver et inkassovarsel på bokmål fra et inkassobyra til en skyldner, jf. "
            "inkassoloven. Bruk brevformat med feltoverskrifter (Til, Fødselsnummer, Adresse, "
            "Saksnummer, Beløp, Dato) og deretter en kort begrunnende tekst.\n\n"
            "Bruk NØYAKTIG disse verdiene, ordrett:\n"
            "- Navn: Rune Fagerheim Dahl\n"
            "- Fødselsnummer: 09027834521\n"
            "- Adresse: Lundveien 21\n"
            "- Postnummer og sted: 3050 Mjøndalen\n"
            "- Saksnummer: INK-2026-771402\n"
            "- Beløp: 62 450 kroner\n"
            "- Dato: 27.03.2026\n\n"
            "I teksten skal folgende to setninger sta verbatim, ordrett:\n"
            "1. \"har inngatt en nedbetalingsavtale som misligholdes for andre gang\"\n"
            "2. \"er registrert med betalingsanmerkning hos tre andre kreditorer\"\n\n"
            "Skriv ca. 250-350 ord, formelt inkassospråk. Ingen engelsk, ingen plassholdere."
        ),
    },
    {
        "id": "P08_vet_inspection_nn",
        "genre": "veterinary inspection order",
        "lang": "nn",
        "marked": False,
        "values": {
            "owner_name": "Bjorn Tallak Oyen",
            "farm_org_number": "912345678",
            "address": "Setervegen 14",
            "postal": "2900 Fagernes",
            "case_number": "MT-2026-4471",
            "date": "09.05.2026",
            "inspector": "veterinær Kristin Sando",
        },
        "clauses": [
            "har gjentekne avvik på forsvarleg husdyrhald sidan 2023",
            "fekk pålegg om utbetring innan fire veker etter forrige tilsyn",
        ],
        "instruction": (
            "Du skriv eit tilsynsvedtak/pålegg fra Mattilsynet til ein dyreeigar, på NYNORSK. "
            "Bruk skjemaformat med feltoverskrifter (Eigar, Org.nr, Adresse, Saksnummer, Dato, "
            "Tilsynsperson) og deretter nummererte pålegg.\n\n"
            "Bruk NØYAKTIG desse verdiane, ordrett:\n"
            "- Eigar: Bjorn Tallak Oyen\n"
            "- Organisasjonsnummer: 912345678\n"
            "- Adresse: Setervegen 14\n"
            "- Postnummer og stad: 2900 Fagernes\n"
            "- Saksnummer: MT-2026-4471\n"
            "- Dato: 09.05.2026\n"
            "- Tilsynsperson: veterinær Kristin Sando\n\n"
            "I grunngjevinga skal desse to setningane sta verbatim, ordrett, IKKJE omsette til bokmål:\n"
            "1. \"har gjentekne avvik på forsvarleg husdyrhald sidan 2023\"\n"
            "2. \"fekk pålegg om utbetring innan fire veker etter forrige tilsyn\"\n\n"
            "Skriv heile vedtaket på nynorsk, ca. 300-400 ord. Ingen engelsk, ingen plasshaldarar."
        ),
    },
    {
        "id": "P09_gp_referral_marked_nb",
        "genre": "GP referral (marked generation)",
        "lang": "nb",
        "marked": True,
        "values": {
            "patient_name": "Hilde Marie Tveit",
            "fnr": "21036512398",
            "address": "Furuveien 5",
            "postal": "1440 Drøbak",
            "phone": "+47 92345671",
            "date": "02.06.2026",
        },
        "marker_types": ["HEALTH", "HEALTH"],
        "instruction": (
            "Du er fastlege og skal skrive en henvisning til spesialisthelsetjenesten på bokmål. "
            "Bruk skjemaformat med feltoverskrifter (Pasient, Fødselsnummer, Adresse, Telefon, "
            "Dato) og deretter en anamnesetekst du selv formulerer.\n\n"
            "Bruk NØYAKTIG disse verdiene, ordrett:\n"
            "- Pasient: Hilde Marie Tveit\n"
            "- Fødselsnummer: 21036512398\n"
            "- Adresse: Furuveien 5\n"
            "- Postnummer og sted: 1440 Drøbak\n"
            "- Telefon: +47 92345671\n"
            "- Dato: 02.06.2026\n\n"
            "I anamnesen skal du SELV formulere to setninger om pasientens helsetilstand "
            "(diagnose og medisinbruk er opp til deg a finne på). Hver av disse to setningene "
            "skal du pakke inn i markorer på formen ⟦HEALTH: setningen her⟦, slik at "
            "hele den sensitive setningen star mellom ⟦HEALTH: og ⟦. Bruk denne "
            "markoren nøyaktig to ganger, en gang per setning. Ikke bruk markoren til noe annet "
            "i teksten.\n\n"
            "Skriv ca. 250-350 ord. Ingen engelsk, ingen plassholdere."
        ),
    },
    {
        "id": "P10_police_report_marked_nn",
        "genre": "police report (marked generation)",
        "lang": "nn",
        "marked": True,
        "values": {
            "suspect_name": "Vetle Skogen Aas",
            "fnr": "30117045612",
            "address": "Elvegata 6",
            "postal": "6900 Florø",
            "case_number": "2026/00987-2",
            "date": "11.07.2026",
        },
        "marker_types": ["CRIMINAL", "CRIMINAL"],
        "instruction": (
            "Du er politibetjent og skal skrive ein anmeldingsrapport på NYNORSK, som løpande "
            "prosatekst.\n\n"
            "Bruk NØYAKTIG desse verdiane, ordrett:\n"
            "- Mistenkt: Vetle Skogen Aas\n"
            "- Fødselsnummer: 30117045612\n"
            "- Adresse: Elvegata 6\n"
            "- Postnummer og stad: 6900 Florø\n"
            "- Saksnummer: 2026/00987-2\n"
            "- Dato: 11.07.2026\n\n"
            "I teksten om tidlegare forhold skal du SJØLV formulere to setningar om mistenktes "
            "kriminelle historikk (finn sjølv på eit realistisk lovbrot og årstal). Kvar av desse "
            "to setningane skal pakkast inn i markorar på forma ⟦CRIMINAL: setninga her⟦. "
            "Bruk denne markoren nøyaktig to gonger. Skriv heile rapporten på nynorsk, IKKJE bokmål.\n\n"
            "Skriv ca. 300-400 ord. Ingen engelsk, ingen plasshaldarar."
        ),
    },
    {
        "id": "P11_nav_decision_marked_nb",
        "genre": "NAV benefit decision (marked generation)",
        "lang": "nb",
        "marked": True,
        "values": {
            "recipient_name": "Ole Kristian Stromme",
            "fnr": "14098034127",
            "address": "Bekkeveien 17",
            "postal": "1601 Fredrikstad",
            "case_number": "NAV-2026-91470",
            "date": "19.08.2026",
        },
        "marker_types": ["ECONOMIC_STATUS", "EMPLOYMENT"],
        "instruction": (
            "Du skriver et NAV-vedtaksbrev på bokmål. Bruk brevformat med feltoverskrifter (Til, "
            "Fødselsnummer, Adresse, Saksnummer, Dato) og deretter en begrunnelse du selv "
            "formulerer.\n\n"
            "Bruk NØYAKTIG disse verdiene, ordrett:\n"
            "- Navn: Ole Kristian Stromme\n"
            "- Fødselsnummer: 14098034127\n"
            "- Adresse: Bekkeveien 17\n"
            "- Postnummer og sted: 1601 Fredrikstad\n"
            "- Saksnummer: NAV-2026-91470\n"
            "- Dato: 19.08.2026\n\n"
            "I begrunnelsen skal du SELV formulere:\n"
            "1. en setning om personens økonomiske situasjon, pakket i ⟦ECONOMIC_STATUS: "
            "setningen her⟦\n"
            "2. en setning om personens arbeidsforhold, pakket i ⟦EMPLOYMENT: setningen "
            "her⟦\n"
            "Bruk hver markortype nøyaktig en gang.\n\n"
            "Skriv ca. 250-350 ord. Ingen engelsk, ingen plassholdere."
        ),
    },
]

if __name__ == "__main__":
    print(f"{len(PROMPTS)} prompts defined")
    for p in PROMPTS:
        print(p["id"], p["genre"], p["lang"], "marked" if p["marked"] else "seeded")
