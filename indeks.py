"""
Indeksering og søk i saksdokumenter (PDF, Word, tekst) og Lovdata-lover.

Alt lagres lokalt i én SQLite-fil. Ingen dokumenter sendes noe sted av
denne modulen – det er bare de utdragene KI-assistenten ber om via
MCP-verktøyene som forlater maskinen.

Mappestruktur som forventes:
    DOKUMENTMAPPE/
        <saksnavn>/   <- første mappenivå tolkes som sak
            kontrakt.pdf
            korrespondanse/epost.docx
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

STOTTEDE_FILER = {".pdf", ".docx", ".txt", ".md"}
MAKS_TEGN_PER_BIT = 2500  # lange sider deles opp, men beholder sidetallet
UTEN_SAK = "(uten sak)"

# Vanlige norske småord som ikke hjelper søket (fjernes fra spørringen)
STOPPORD = {
    "og", "i", "på", "til", "for", "med", "av", "som", "den", "det", "de",
    "en", "et", "ei", "er", "var", "har", "om", "at", "fra", "ved", "eller",
    "hva", "hvor", "hvem", "hvordan", "når", "sier", "står", "finnes", "noe",
    "alle", "skal", "kan", "vil", "må", "ikke", "seg", "sin", "sitt", "sine",
    "denne", "dette", "disse", "the", "and", "of", "to", "in",
}


# ---------------------------------------------------------------- database

def koble_til(db_sti: str | Path) -> sqlite3.Connection:
    # MCP-serveren kjører verktøy i tråder; serveren serialiserer tilgang med en lås
    con = sqlite3.connect(str(db_sti), check_same_thread=False)
    con.row_factory = sqlite3.Row
    _opprett_skjema(con)
    return con


def _tokenizer(con: sqlite3.Connection) -> str:
    """Trigram-tokenizer gir treff inne i norske sammensatte ord
    («begrensning» finner «ansvarsbegrensning»). Krever SQLite 3.34+."""
    try:
        con.execute("CREATE VIRTUAL TABLE temp._t USING fts5(x, tokenize='trigram')")
        con.execute("DROP TABLE temp._t")
        return "trigram"
    except sqlite3.OperationalError:
        return "unicode61 remove_diacritics 0"


def _opprett_skjema(con: sqlite3.Connection) -> None:
    tok = _tokenizer(con)
    con.executescript(f"""
        CREATE TABLE IF NOT EXISTS dokumenter (
            id     INTEGER PRIMARY KEY,
            sak    TEXT NOT NULL,
            fil    TEXT NOT NULL,     -- sti relativt til saksmappen
            sti    TEXT NOT NULL UNIQUE,
            type   TEXT NOT NULL,
            mtime  REAL NOT NULL,
            enheter INTEGER NOT NULL  -- antall sider/deler
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS biter USING fts5(
            tekst,
            dok_id UNINDEXED, sak UNINDEXED, fil UNINDEXED,
            enhet UNINDEXED, nr UNINDEXED,
            tokenize = "{tok}"
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS lover USING fts5(
            tekst, tittel,
            lov_id UNINDEXED, korttittel UNINDEXED, paragraf UNINDEXED,
            tokenize = "{tok}"
        );
        CREATE TABLE IF NOT EXISTS meta (nokkel TEXT PRIMARY KEY, verdi TEXT);
    """)
    con.commit()


# ---------------------------------------------------------- tekstuttrekk

@dataclass
class Bit:
    enhet: str   # "side" eller "del"
    nr: int
    tekst: str


def _del_opp(tekst: str, enhet: str, nr: int) -> list[Bit]:
    tekst = re.sub(r"[ \t]+", " ", tekst).strip()
    if not tekst:
        return []
    if len(tekst) <= MAKS_TEGN_PER_BIT:
        return [Bit(enhet, nr, tekst)]
    deler, start = [], 0
    while start < len(tekst):
        slutt = min(start + MAKS_TEGN_PER_BIT, len(tekst))
        if slutt < len(tekst):  # prøv å kutte ved avsnitt/punktum
            kutt = max(tekst.rfind("\n", start, slutt), tekst.rfind(". ", start, slutt))
            if kutt > start + MAKS_TEGN_PER_BIT // 2:
                slutt = kutt + 1
        deler.append(Bit(enhet, nr, tekst[start:slutt].strip()))
        start = slutt
    return deler


def trekk_ut_tekst(sti: Path) -> list[Bit]:
    """Returnerer tekstbiter med sidetall (PDF) eller delnummer (Word/tekst)."""
    ending = sti.suffix.lower()
    if ending == ".pdf":
        from pypdf import PdfReader
        biter: list[Bit] = []
        for i, side in enumerate(PdfReader(str(sti)).pages, start=1):
            biter += _del_opp(side.extract_text() or "", "side", i)
        return biter

    if ending == ".docx":
        import docx
        d = docx.Document(str(sti))
        avsnitt = [p.text for p in d.paragraphs if p.text.strip()]
        for tabell in d.tables:
            for rad in tabell.rows:
                avsnitt.append(" | ".join(c.text.strip() for c in rad.cells))
        return _grupper_avsnitt(avsnitt)

    # .txt / .md
    tekst = sti.read_text(encoding="utf-8", errors="replace")
    return _grupper_avsnitt([a for a in tekst.split("\n\n") if a.strip()])


def _grupper_avsnitt(avsnitt: list[str]) -> list[Bit]:
    """Word har ikke faste sider, så vi lager nummererte deler på ~1 side."""
    biter, buffer, nr = [], "", 1
    for a in avsnitt:
        if buffer and len(buffer) + len(a) > MAKS_TEGN_PER_BIT:
            biter += _del_opp(buffer, "del", nr)
            buffer, nr = "", nr + 1
        buffer += a + "\n"
    if buffer.strip():
        biter += _del_opp(buffer, "del", nr)
    return biter


# ------------------------------------------------------------ indeksering

def oppdater_indeks(con: sqlite3.Connection, mappe: str | Path) -> dict:
    """Inkrementell indeksering: bare nye/endrede filer leses på nytt,
    og filer som er slettet fra mappen fjernes fra indeksen."""
    mappe = Path(mappe).expanduser().resolve()
    if not mappe.is_dir():
        raise FileNotFoundError(f"Fant ikke dokumentmappen: {mappe}")

    funnet: set[str] = set()
    nye = endret = feilet = 0
    feil: list[str] = []

    for sti in sorted(mappe.rglob("*")):
        if not sti.is_file() or sti.suffix.lower() not in STOTTEDE_FILER:
            continue
        if any(del_.startswith(".") or del_.startswith("~$") for del_ in sti.relative_to(mappe).parts):
            continue
        rel = sti.relative_to(mappe)
        sak = rel.parts[0] if len(rel.parts) > 1 else UTEN_SAK
        fil = str(Path(*rel.parts[1:])) if len(rel.parts) > 1 else rel.name
        nokkel = str(sti)
        funnet.add(nokkel)
        mtime = sti.stat().st_mtime

        rad = con.execute("SELECT id, mtime FROM dokumenter WHERE sti=?", (nokkel,)).fetchone()
        if rad and abs(rad["mtime"] - mtime) < 1e-6:
            continue

        try:
            biter = trekk_ut_tekst(sti)
        except Exception as e:  # ødelagt/kryptert fil – hopp over, men rapporter
            feilet += 1
            feil.append(f"{sak}/{fil}: {e.__class__.__name__}")
            continue

        if rad:
            con.execute("DELETE FROM biter WHERE dok_id=?", (rad["id"],))
            con.execute("DELETE FROM dokumenter WHERE id=?", (rad["id"],))
            endret += 1
        else:
            nye += 1

        enheter = max((b.nr for b in biter), default=0)
        cur = con.execute(
            "INSERT INTO dokumenter (sak, fil, sti, type, mtime, enheter) VALUES (?,?,?,?,?,?)",
            (sak, fil, nokkel, sti.suffix.lower().lstrip("."), mtime, enheter),
        )
        con.executemany(
            "INSERT INTO biter (tekst, dok_id, sak, fil, enhet, nr) VALUES (?,?,?,?,?,?)",
            [(b.tekst, cur.lastrowid, sak, fil, b.enhet, b.nr) for b in biter],
        )

    fjernet = 0
    for rad in con.execute("SELECT id, sti FROM dokumenter").fetchall():
        if rad["sti"] not in funnet and rad["sti"].startswith(str(mappe)):
            con.execute("DELETE FROM biter WHERE dok_id=?", (rad["id"],))
            con.execute("DELETE FROM dokumenter WHERE id=?", (rad["id"],))
            fjernet += 1

    con.execute("INSERT OR REPLACE INTO meta VALUES ('sist_indeksert', ?)", (time.strftime("%Y-%m-%d %H:%M"),))
    con.commit()
    totalt = con.execute("SELECT COUNT(*) FROM dokumenter").fetchone()[0]
    return {"nye": nye, "endret": endret, "fjernet": fjernet, "feilet": feilet,
            "feil": feil, "dokumenter_totalt": totalt}


# ------------------------------------------------------------------ søk

def _sokeord(sporring: str) -> list[str]:
    ord_ = re.findall(r"[\wæøåÆØÅ§\-\.]+", sporring.lower())
    ord_ = [o.strip(".-") for o in ord_]
    return [o for o in ord_ if len(o) >= 3 and o not in STOPPORD]


def _fts_uttrykk(ord_: list[str], operator: str) -> str:
    return f" {operator} ".join('"' + o.replace('"', "") + '"' for o in ord_)


def _utdrag(tekst: str, ord_: list[str], for_: int = 150, etter: int = 350) -> str:
    """Kort utdrag rundt første treff, med hele treffordet markert «slik»."""
    lav = tekst.lower()
    pos = min((p for p in (lav.find(o) for o in ord_) if p >= 0), default=0)
    start, slutt = max(0, pos - for_), min(len(tekst), pos + etter)
    biten = tekst[start:slutt].replace("\n", " ")
    monster = "|".join(re.escape(o) for o in sorted(set(ord_), key=len, reverse=True))
    biten = re.sub(rf"(\w*(?:{monster})\w*)", r"«\1»", biten, flags=re.IGNORECASE)
    return ("… " if start > 0 else "") + biten.strip() + (" …" if slutt < len(tekst) else "")


def _kjor_sok(con, tabell: str, ord_: list[str], ekstra_sql: str, param: list, maks: int):
    """Prøver først at ALLE ord må finnes (presist), deretter NOEN (bredt)."""
    for operator, modus in (("AND", "alle ord"), ("OR", "noen av ordene")):
        sql = (f"SELECT *, bm25({tabell}) AS score FROM {tabell} "
               f"WHERE {tabell} MATCH ? {ekstra_sql} ORDER BY score LIMIT ?")
        rader = con.execute(sql, [_fts_uttrykk(ord_, operator), *param, maks]).fetchall()
        if rader or len(ord_) == 1:
            return rader, modus
    return [], "noen av ordene"


def sok_dokumenter(con, sporring: str, sak: str | None = None,
                   tillatte_saker: set[str] | None = None, maks_treff: int = 8) -> dict:
    ord_ = _sokeord(sporring)
    if not ord_:
        return {"treff": [], "merknad": "Spørringen inneholdt ingen søkbare ord (minst 3 tegn)."}

    filtre, param = [], []
    if sak:
        filtre.append("AND sak = ?")
        param.append(sak)
    if tillatte_saker is not None:
        filtre.append(f"AND sak IN ({','.join('?' * len(tillatte_saker))})" if tillatte_saker else "AND 0")
        param += sorted(tillatte_saker)

    rader, modus = _kjor_sok(con, "biter", ord_, " ".join(filtre), param, maks_treff)
    treff = [{
        "kilde": f"{r['sak']} / {r['fil']}, {r['enhet']} {r['nr']}",
        "dok_id": r["dok_id"], "sak": r["sak"], "fil": r["fil"],
        "enhet": r["enhet"], "nr": r["nr"],
        "utdrag": _utdrag(r["tekst"], ord_),
    } for r in rader]
    return {"spørring": sporring, "søkeord": ord_, "treffmodus": modus, "treff": treff}


def hent_tekst(con, dok_id: int, nr: int, tillatte_saker: set[str] | None = None) -> dict:
    dok = con.execute("SELECT * FROM dokumenter WHERE id=?", (dok_id,)).fetchone()
    if not dok or (tillatte_saker is not None and dok["sak"] not in tillatte_saker):
        return {"feil": f"Fant ikke dokument {dok_id} (eller du har ikke tilgang)."}
    rader = con.execute("SELECT enhet, tekst FROM biter WHERE dok_id=? AND nr=?", (dok_id, nr)).fetchall()
    if not rader:
        return {"feil": f"{dok['fil']} har ikke {nr}. Dokumentet har {dok['enheter']} side(r)/del(er)."}
    enhet = rader[0]["enhet"]
    return {"kilde": f"{dok['sak']} / {dok['fil']}, {enhet} {nr}",
            "antall": f"{enhet} {nr} av {dok['enheter']}",
            "tekst": "\n".join(r["tekst"] for r in rader)}


def liste_saker(con, tillatte_saker: set[str] | None = None) -> list[dict]:
    rader = con.execute("""SELECT sak, COUNT(*) AS antall, GROUP_CONCAT(fil, ' | ') AS filer
                           FROM dokumenter GROUP BY sak ORDER BY sak""").fetchall()
    return [{"sak": r["sak"], "antall_dokumenter": r["antall"],
             "dokumenter": [{"fil": f} for f in r["filer"].split(" | ")]}
            for r in rader if tillatte_saker is None or r["sak"] in tillatte_saker]


def liste_dokumenter(con, sak: str) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT id AS dok_id, fil, type, enheter AS antall_sider_eller_deler FROM dokumenter WHERE sak=? ORDER BY fil",
        (sak,))]


def sok_lover(con, sporring: str, maks_treff: int = 6) -> dict:
    if con.execute("SELECT COUNT(*) FROM lover").fetchone()[0] == 0:
        return {"treff": [], "merknad": "Lovdata er ikke lastet ned ennå. Kjør: python lovdata_sync.py"}
    ord_ = _sokeord(sporring)
    if not ord_:
        return {"treff": [], "merknad": "Ingen søkbare ord."}
    rader, modus = _kjor_sok(con, "lover", ord_, "", [], maks_treff)
    sist = con.execute("SELECT verdi FROM meta WHERE nokkel='lovdata_hentet'").fetchone()
    return {
        "spørring": sporring, "treffmodus": modus,
        "lovdata_hentet": sist["verdi"] if sist else None,
        "treff": [{
            "kilde": f"{r['korttittel'] or r['tittel']} {r['paragraf']}".strip(),
            "lov_id": r["lov_id"],
            "lenke": f"https://lovdata.no/dokument/{r['lov_id']}" if r["lov_id"] else None,
            "tekst": r["tekst"][:1500],
        } for r in rader],
    }


# --------------------------------------------------------------- logging

def logg(loggfil: str | Path | None, verktoy: str, **data) -> None:
    """Enkel revisjonslogg (hvem søkte på hva) – nyttig for internkontroll."""
    if not loggfil:
        return
    rad = {"tid": time.strftime("%Y-%m-%dT%H:%M:%S"), "bruker": os.environ.get("USER") or os.environ.get("USERNAME") or "?",
           "verktøy": verktoy, **data}
    with open(loggfil, "a", encoding="utf-8") as f:
        f.write(json.dumps(rad, ensure_ascii=False) + "\n")


if __name__ == "__main__":  # python indeks.py <mappe>  – indekser fra kommandolinjen
    import sys
    mappe = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("JUSS_DOKUMENTMAPPE", "dokumenter")
    db = os.environ.get("JUSS_DB", str(Path(__file__).with_name("juss_sok.db")))
    print(json.dumps(oppdater_indeks(koble_til(db), mappe), ensure_ascii=False, indent=2))
