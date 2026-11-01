"""
Lager fiktive saksdokumenter for demo og testing. Alle navn, selskaper
og saker er oppdiktet. Kjør: python lag_eksempeldata.py
"""

from pathlib import Path

import docx
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

UT = Path(__file__).resolve().parent / "eksempeldokumenter"
STIL = getSampleStyleSheet()


def pdf(sti: Path, sider: list[list[str]]) -> None:
    sti.parent.mkdir(parents=True, exist_ok=True)
    innhold = []
    for i, side in enumerate(sider):
        for j, avsnitt in enumerate(side):
            innhold.append(Paragraph(avsnitt, STIL["Heading2"] if j == 0 else STIL["BodyText"]))
            innhold.append(Spacer(1, 6))
        if i < len(sider) - 1:
            innhold.append(PageBreak())
    SimpleDocTemplate(str(sti), pagesize=A4).build(innhold)


def word(sti: Path, tittel: str, avsnitt: list[str]) -> None:
    sti.parent.mkdir(parents=True, exist_ok=True)
    d = docx.Document()
    d.add_heading(tittel, level=1)
    for a in avsnitt:
        d.add_paragraph(a)
    d.save(str(sti))


def main() -> None:
    # ---------------------------------------------------------------- sak 1
    s1 = UT / "2026-014 Fjordbyen Eiendom - leietvist"
    pdf(s1 / "Leiekontrakt Strandgata 12.pdf", [
        ["Leiekontrakt for næringslokaler",
         "Mellom Fjordbyen Eiendom AS (utleier) og Kaffebrenneriet Vest AS (leietaker) er det inngått "
         "avtale om leie av lokaler i Strandgata 12, 1. etasje, til bruk som kafé og brenneri.",
         "1. Leieperiode. Leieforholdet løper fra 1. mars 2024 til 28. februar 2034. Leietaker har rett "
         "til forlengelse i fem år på samme vilkår, forutsatt skriftlig varsel senest tolv måneder før utløp.",
         "2. Leie. Årlig leie er kr 840 000 eksklusive merverdiavgift, og betales kvartalsvis forskuddsvis."],
        ["Vedlikehold og mangler",
         "5. Vedlikehold. Utleier har ansvar for utvendig vedlikehold, tak, bærende konstruksjoner og "
         "tekniske anlegg frem til leietakers fordelingspunkt. Leietaker har ansvar for innvendig vedlikehold.",
         "6. Mangler. Leietaker skal reklamere skriftlig uten ugrunnet opphold etter at en mangel er eller "
         "burde vært oppdaget. Ved vesentlige fuktskader som hindrer bruk av lokalene, har leietaker krav på "
         "forholdsmessig avslag i leien fra reklamasjonstidspunktet.",
         "7. Ansvarsbegrensning. Utleier er ikke ansvarlig for leietakers driftstap eller indirekte tap, "
         "med mindre tapet skyldes grov uaktsomhet eller forsett hos utleier."],
        ["Tvisteløsning",
         "12. Verneting. Tvister som ikke løses ved forhandlinger, avgjøres av de ordinære domstoler med "
         "Sør-Rogaland tingrett som avtalt verneting.",
         "Kontrakten er undertegnet i to eksemplarer, hvorav partene beholder hvert sitt."],
    ])
    word(s1 / "Korrespondanse" / "E-post fra klient 2026-08-19.docx", "E-post fra Kaffebrenneriet Vest AS", [
        "Hei. Vi har siden juni hatt vanninntrenging fra taket over brenneriet. Vi meldte fra muntlig "
        "til vaktmester i juni og sendte skriftlig reklamasjon 14. august.",
        "Brenneriet har vært stengt i tre uker, og vi anslår driftstapet til rundt kr 310 000. "
        "Utleier sier at kontraktens punkt 7 utelukker krav på driftstap.",
        "Kan dere vurdere om vi kan kreve prisavslag og erstatning, og om utleier har vært grovt uaktsom "
        "ved å ignorere varselet i juni?",
    ])

    # ---------------------------------------------------------------- sak 2
    s2 = UT / "2026-021 Nordlys Data - IT-avtale"
    pdf(s2 / "Avtale om utvikling av saksbehandlingssystem.pdf", [
        ["Avtale om utvikling og levering av programvare",
         "Avtalen er inngått mellom Sandnes Kommunale Boligselskap KF (kunden) og Nordlys Data AS "
         "(leverandøren) om utvikling av et digitalt saksbehandlingssystem.",
         "3. Leveranse og frister. Godkjenningsprøve skal være gjennomført innen 1. juni 2026."],
        ["Forsinkelse og dagbøter",
         "9. Dagbøter. Ved forsinkelse med godkjenningsprøven påløper dagbøter med 0,15 % av avtalt "
         "vederlag per kalenderdag, begrenset til 100 kalenderdager.",
         "10. Ansvarsbegrensning. Leverandørens samlede erstatningsansvar er begrenset til 100 % av "
         "avtalt vederlag. Begrensningen gjelder ikke ved grov uaktsomhet eller forsett.",
         "11. Heving. Dersom dagbøter har løpt i maksimal periode, kan kunden heve avtalen."],
    ])
    word(s2 / "Møtereferat 2026-09-02.docx", "Referat fra statusmøte 2. september 2026", [
        "Til stede: prosjektleder hos kunden og daglig leder i Nordlys Data AS.",
        "Leverandøren erkjente at godkjenningsprøven ikke er gjennomført, og anslår ny dato til 15. november.",
        "Kunden tok forbehold om å kreve dagbøter fra 2. juni og vurderer heving.",
    ])

    # ---------------------------------------------------------------- sak 3
    s3 = UT / "2026-033 Ola Hansen - oppsigelse"
    pdf(s3 / "Arbeidsavtale.pdf", [
        ["Arbeidsavtale",
         "Ola Hansen er ansatt som prosjektingeniør i Vestkyst Offshore Service AS fra 1. januar 2019.",
         "Oppsigelsesfristen er tre måneder regnet fra den første dag i måneden etter at oppsigelsen er mottatt.",
         "Arbeidstaker har konkurranseklausul i seks måneder etter fratreden, jf. arbeidsmiljøloven kapittel 14 A."],
    ])
    word(s3 / "Oppsigelsesbrev.docx", "Oppsigelse", [
        "Vi viser til drøftelsesmøte 3. september 2026. Det er besluttet å si deg opp på grunn av "
        "nedbemanning som følge av redusert oppdragsmengde.",
        "Utvelgelsen er basert på ansiennitet, kompetanse og sosiale forhold.",
        "Du har rett til å kreve forhandlinger og til å fortsette i stillingen mens saken pågår.",
    ])
    (s3 / "Notat fra klientmøte.txt").write_text(
        "Klienten mener utvelgelsen var usaklig fordi to kolleger med kortere ansiennitet beholdt jobben.\n\n"
        "Klienten fikk ikke informasjon om ledige stillinger i konsernet før oppsigelsen.\n\n"
        "Frist for å kreve forhandlinger er to uker etter at oppsigelsen ble mottatt.",
        encoding="utf-8",
    )
    print(f"Eksempeldokumenter laget i {UT}")


if __name__ == "__main__":
    main()
