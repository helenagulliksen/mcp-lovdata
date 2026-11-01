"""
juss-sok: MCP-server for søk i saksdokumenter og norsk lovverk.

Miljøvariabler:
  JUSS_DOKUMENTMAPPE  mappen med saker (påkrevd), én undermappe per sak
  JUSS_DB             SQLite-indeksen (standard: juss_sok.db ved siden av denne filen)
  JUSS_TILGANG        valgfri kommaliste med saker brukeren har tilgang til
                      (demonstrerer «etiske vegger» – andre saker blir usynlige)
  JUSS_LOGG           valgfri sti til revisjonslogg (JSON Lines)
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer

import indeks

HER = Path(__file__).resolve().parent
MAPPE = os.environ.get("JUSS_DOKUMENTMAPPE", str(HER / "eksempeldokumenter"))
DB = os.environ.get("JUSS_DB", str(HER / "juss_sok.db"))
LOGG = os.environ.get("JUSS_LOGG") or None
_tilgang = os.environ.get("JUSS_TILGANG", "").strip()
TILLATTE = {s.strip() for s in _tilgang.split(",") if s.strip()} if _tilgang else None

con = indeks.koble_til(DB)
LAS = threading.Lock()  # én SQLite-forbindelse deles av verktøy-trådene
try:
    indeks.oppdater_indeks(con, MAPPE)  # rask når ingenting er endret
except FileNotFoundError:
    pass

mcp = MCPServer(
    "juss-sok",
    instructions=(
        "Søkeverktøy for et advokatkontors saksdokumenter og norske lover/forskrifter. "
        "Regler for bruk: (1) Bygg svar KUN på tekst verktøyene returnerer, og oppgi alltid "
        "kilden i formatet [sak / fil, side N] eller [lov § N] etter hver påstand. "
        "(2) Finner du ikke noe, si det rett ut – aldri gjett eller fyll inn fra hukommelsen. "
        "(3) Bruk hent_tekst for å lese hele siden før du siterer eller konkluderer. "
        "(4) Søk med nøkkelord, ikke hele setninger, og prøv synonymer hvis første søk gir lite."
    ),
)


@mcp.tool()
def sok_dokumenter(sporring: str, sak: str | None = None, maks_treff: int = 8) -> dict:
    """Fulltekstsøk i saksdokumentene. Treffer også inne i sammensatte ord
    (f.eks. 'begrensning' finner 'ansvarsbegrensning').

    Args:
        sporring: 1–5 nøkkelord, f.eks. 'ansvarsbegrensning erstatning' eller 'oppsigelse frist'.
        sak: valgfritt – begrens til én sak (navn fra liste_saker).
        maks_treff: antall treff (standard 8).
    Returnerer treff med kilde (sak/fil/side), dok_id og et kort utdrag.
    """
    with LAS:
        svar = indeks.sok_dokumenter(con, sporring, sak, TILLATTE, min(maks_treff, 25))
    indeks.logg(LOGG, "sok_dokumenter", sporring=sporring, sak=sak, treff=len(svar["treff"]))
    return svar


@mcp.tool()
def hent_tekst(dok_id: int, nr: int) -> dict:
    """Henter full tekst for én side (PDF) eller del (Word) av et dokument.
    Bruk dok_id og nr fra et søketreff."""
    with LAS:
        svar = indeks.hent_tekst(con, dok_id, nr, TILLATTE)
    indeks.logg(LOGG, "hent_tekst", dok_id=dok_id, nr=nr)
    return svar


@mcp.tool()
def liste_saker() -> list[dict]:
    """Lister sakene brukeren har tilgang til, med dokumentene i hver sak."""
    with LAS:
        return indeks.liste_saker(con, TILLATTE)


@mcp.tool()
def liste_dokumenter(sak: str) -> list[dict]:
    """Lister dokumentene i én sak med dok_id og antall sider/deler,
    slik at et helt dokument kan leses side for side med hent_tekst."""
    if TILLATTE is not None and sak not in TILLATTE:
        return []
    with LAS:
        return indeks.liste_dokumenter(con, sak)


@mcp.tool()
def sok_lovverk(sporring: str, maks_treff: int = 6) -> dict:
    """Søk i gjeldende norske lover og sentrale forskrifter (Lovdatas åpne data,
    lokal kopi). Returnerer paragrafer med lenke til lovdata.no. Kontroller alltid
    mot Lovdata før bruk – den lokale kopien kan være noen dager gammel."""
    with LAS:
        svar = indeks.sok_lover(con, sporring, min(maks_treff, 20))
    indeks.logg(LOGG, "sok_lovverk", sporring=sporring, treff=len(svar["treff"]))
    return svar


@mcp.tool()
def oppdater_indeks() -> dict:
    """Leser inn nye og endrede filer i dokumentmappen (kjør etter at du har lagt til dokumenter)."""
    with LAS:
        return indeks.oppdater_indeks(con, MAPPE)


if __name__ == "__main__":
    mcp.run()
