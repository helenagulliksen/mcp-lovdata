# juss-sok

En MCP-server som lar en KI-assistent (f.eks. Claude Desktop) søke i et advokatkontors
saksdokumenter og i norsk lovverk, med kildehenvisning til fil og side i hvert svar.

Prototypen er laget for å vise hvordan KI kan brukes i juridisk arbeid uten å gi slipp på
det som betyr mest i en advokatvirksomhet: **taushetsplikt, etterprøvbarhet og tilgangskontroll**.

> Eksempel: «Hvilke av sakene våre har ansvarsbegrensning som ikke gjelder ved grov uaktsomhet?»
> → Assistenten søker, leser de relevante sidene og svarer med henvisninger som
> *[2026-021 Nordlys Data / Avtale om utvikling … .pdf, side 2]*.

## Hva den gjør

| Verktøy | Funksjon |
|---|---|
| `liste_saker` | Viser sakene brukeren har tilgang til |
| `sok_dokumenter` | Fulltekstsøk i PDF, Word og tekst, med utdrag og kilde (sak / fil / side) |
| `hent_tekst` | Leser en hel side, slik at svaret bygger på hele konteksten, ikke bare et utdrag |
| `liste_dokumenter` | Viser dokumentene i én sak med sidetall |
| `sok_lovverk` | Søk i gjeldende lover og sentrale forskrifter (Lovdatas åpne data), med lenke til lovdata.no |
| `oppdater_indeks` | Leser inn nye og endrede filer |

## Designvalg

- **Kildehenvisning som krav.** Serveren instruerer assistenten om å svare kun på grunnlag av
  tekst den har hentet, oppgi kilde etter hver påstand og si tydelig fra når den ikke finner noe.
  Det er et tiltak mot oppdiktede kilder, som er den mest kjente feilen ved KI-bruk i juridisk arbeid.
- **Alt lagres lokalt.** Indeksen er én SQLite-fil på egen maskin. Ingen dokumenter lastes opp
  noe sted; bare utdragene assistenten faktisk ber om forlater maskinen.
- **Etiske vegger.** Med `JUSS_TILGANG` begrenses brukeren til bestemte saker, og andre saker
  blir helt usynlige i søk, lister og oppslag. I en ekte løsning hentes dette fra DMS-et.
- **Revisjonslogg.** Med `JUSS_LOGG` logges hvem som søkte på hva og når, til bruk i internkontroll.
- **Norske sammensatte ord.** Søket bruker trigram-indeksering, slik at «begrensning» også
  finner «ansvarsbegrensning» og «frist» finner «oppsigelsesfristen».
- **Presist før bredt.** Søket krever først at alle søkeordene finnes, og utvider bare hvis det
  ikke gir treff.

## Kom i gang

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python lag_eksempeldata.py       # tre fiktive saker til testing
python indeks.py eksempeldokumenter
python lovdata_sync.py --bare-lover   # valgfritt: henter lovene fra Lovdata (åpne data, NLOD 2.0)
```

### Koble til Claude Desktop

Åpne Claude Desktop → Innstillinger → Developer → Edit Config, og legg til
(bruk fulle stier, og Python fra `.venv`):

```json
{
  "mcpServers": {
    "juss-sok": {
      "command": "/sti/til/juss-sok/.venv/bin/python",
      "args": ["/sti/til/juss-sok/server.py"],
      "env": {
        "JUSS_DOKUMENTMAPPE": "/sti/til/juss-sok/eksempeldokumenter",
        "JUSS_LOGG": "/sti/til/juss-sok/soklogg.jsonl"
      }
    }
  }
}
```

Start Claude Desktop på nytt. Prøv for eksempel:

- «Hvilke saker har vi, og hva handler de om?»
- «Har leietaker i Fjordbyen-saken krav på erstatning for driftstapet? Se på kontrakten og e-posten.»
- «Når løper fristen for å kreve forhandlinger i Ola Hansen-saken?»
- «Finn bestemmelsene i husleieloven om mangler.» (krever `lovdata_sync.py`)

For å teste etiske vegger, legg til `"JUSS_TILGANG": "2026-021 Nordlys Data - IT-avtale"` under `env`.

## Mappestruktur

```
dokumenter/
  2026-014 Fjordbyen Eiendom - leietvist/     <- én mappe per sak
    Leiekontrakt Strandgata 12.pdf
    Korrespondanse/E-post fra klient.docx
```

## Begrensninger og veien videre

Dette er en prototype og ikke ment for ekte klientdata uten videre vurdering.

- **Semantisk søk:** kombinere fulltekst med embeddings (hybridsøk), slik at «hva skjer hvis
  leverandøren er sen?» også finner «dagbøter».
- **OCR:** skannede PDF-er uten tekstlag blir ikke funnet i dag.
- **DMS-integrasjon:** hente dokumenter og tilganger direkte fra iManage, NetDocuments eller SharePoint.
- **Personvern og leverandør:** før bruk på ekte saker må det vurderes hvilken KI-modell som brukes,
  hvor data behandles, databehandleravtale og forholdet til taushetsplikten.
- **Lovdata-kopien** er et øyeblikksbilde. Kontroller alltid mot lovdata.no før bruk.

Alle navn og saker i `eksempeldokumenter/` er fiktive.
