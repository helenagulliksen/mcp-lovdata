"""
Laster ned Lovdatas åpne datasett (gjeldende lover og sentrale forskrifter,
lisens NLOD 2.0) og indekserer dem paragraf for paragraf.

Ingen API-nøkkel trengs. Kjør ved behov, f.eks. en gang i uken:

    python lovdata_sync.py              # lover + sentrale forskrifter
    python lovdata_sync.py --bare-lover

Endepunkter (åpne): https://api.lovdata.no/v1/publicData/list
                    https://api.lovdata.no/v1/publicData/get/<filnavn>
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import tarfile
import time
import urllib.request
from pathlib import Path

from indeks import koble_til

API = "https://api.lovdata.no/v1/publicData"


def hent(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "juss-sok-prototype/0.1"})
    with urllib.request.urlopen(req, timeout=120) as svar:
        return svar.read()


def _tekst(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def parse_lov(xml: str, filnavn: str) -> tuple[dict, list[tuple[str, str]]]:
    """Returnerer (metadata, [(paragraf, tekst), ...]).

    Lovdatas filer er HTML-lignende XML. Paragrafer ligger normalt i elementer
    med klassen «legalArticle». Finnes ikke disse, faller vi tilbake til å dele
    teksten ved «§»-overskrifter, og til slutt i biter.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(xml, "html.parser")

    meta = {"tittel": "", "korttittel": "", "lov_id": ""}
    # Metadata ligger typisk som <dt class="..">/<dd class=".."> eller i <title>
    for dd in soup.find_all("dd"):
        klasse = " ".join(dd.get("class", []))
        if "titleShort" in klasse and not meta["korttittel"]:
            meta["korttittel"] = _tekst(dd)
        elif "title" in klasse.lower() and not meta["tittel"]:
            meta["tittel"] = _tekst(dd)
        elif klasse in ("dokid", "refid") and not meta["lov_id"]:
            meta["lov_id"] = _tekst(dd)
    if not meta["tittel"] and soup.title:
        meta["tittel"] = _tekst(soup.title)
    if not meta["tittel"]:
        meta["tittel"] = filnavn

    paragrafer: list[tuple[str, str]] = []
    artikler = soup.find_all(class_=re.compile(r"\blegalArticle\b"))
    for art in artikler:
        if art.find_parent(class_=re.compile(r"\blegalArticle\b")):
            continue  # unngå dobbelttelling av nøstede elementer
        nr = art.find(class_=re.compile(r"legalArticleValue"))
        tittel = art.find(class_=re.compile(r"legalArticleTitle"))
        paragraf = (_tekst(nr) if nr else (art.get("data-name") or "")).strip()
        if tittel:
            paragraf = f"{paragraf} {_tekst(tittel)}".strip()
        tekst = _tekst(art)
        if tekst:
            paragrafer.append((paragraf, tekst))

    if not paragrafer:  # reserve: del ved §-overskrifter
        brodtekst = soup.get_text("\n", strip=True)
        deler = re.split(r"\n(?=§\s*\d+[a-z]?\s*\.?)", brodtekst)
        for d in deler:
            m = re.match(r"(§\s*\d+[a-z]?)", d)
            for i in range(0, len(d), 3000):
                paragrafer.append((m.group(1) if m else "", re.sub(r"\s+", " ", d[i:i + 3000])))

    return meta, paragrafer


def synkroniser(db: str, bare_lover: bool = False) -> dict:
    datasett = json.loads(hent(f"{API}/list"))
    onsket = [d for d in datasett if "gjeldende" in d.get("filename", "")
              and (not bare_lover or "lover" in d["filename"])]
    if not onsket:
        raise RuntimeError(f"Fant ikke forventede datasett. Tilgjengelige: {[d.get('filename') for d in datasett]}")

    con = koble_til(db)
    con.execute("DELETE FROM lover")
    antall_dok = antall_par = 0
    for d in onsket:
        navn = d["filename"]
        print(f"Laster ned {navn} …", flush=True)
        arkiv = tarfile.open(fileobj=io.BytesIO(hent(f"{API}/get/{navn}")), mode="r:*")
        for medlem in arkiv:
            if not medlem.isfile() or not medlem.name.endswith((".xml", ".html")):
                continue
            innhold = arkiv.extractfile(medlem).read().decode("utf-8", errors="replace")
            filnavn = Path(medlem.name).stem
            meta, paragrafer = parse_lov(innhold, filnavn)
            lov_id = meta["lov_id"] or _id_fra_filnavn(filnavn)
            con.executemany(
                "INSERT INTO lover (tekst, tittel, lov_id, korttittel, paragraf) VALUES (?,?,?,?,?)",
                [(t, meta["tittel"], lov_id, meta["korttittel"], p) for p, t in paragrafer],
            )
            antall_dok += 1
            antall_par += len(paragrafer)
        print(f"  {antall_dok} dokumenter så langt", flush=True)

    con.execute("INSERT OR REPLACE INTO meta VALUES ('lovdata_hentet', ?)", (time.strftime("%Y-%m-%d"),))
    con.commit()
    return {"dokumenter": antall_dok, "paragrafer": antall_par}


def _id_fra_filnavn(filnavn: str) -> str:
    """nl-19990702-063 -> NL/lov/1999-07-02-63 (brukes til lenke til lovdata.no)"""
    m = re.match(r"(nl|sf)-(\d{4})(\d{2})(\d{2})-(\d+)", filnavn, re.I)
    if not m:
        return ""
    base, aar, mnd, dag, nr = m.groups()
    type_ = "lov" if base.lower() == "nl" else "forskrift"
    return f"{base.upper()}/{type_}/{aar}-{mnd}-{dag}-{int(nr)}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bare-lover", action="store_true", help="Hopp over forskriftene (raskere)")
    args = ap.parse_args()
    db = os.environ.get("JUSS_DB", str(Path(__file__).with_name("juss_sok.db")))
    print(json.dumps(synkroniser(db, args.bare_lover), ensure_ascii=False))
