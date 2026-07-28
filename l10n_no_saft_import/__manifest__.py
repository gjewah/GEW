# Part of FIQ AI. Norsk SAF-T Financial 1.30 import.
{
    'name': 'Norway - SAF-T Import',
    'version': '19.0.1.1.0',
    'category': 'Accounting/Localizations',
    'summary': 'Import Accounting Data from Norwegian SAF-T Financial files',
    'description': """
Norsk SAF-T Financial 1.30 — import
===================================
Utvider Odoos generiske `account_saft_import` slik at den leser norske SAF-T Financial-filer
(namespace `urn:StandardAuditFile-Taxation-Financial:NO`), f.eks. eksport fra PowerOffice Go.
Verifisert mot 19 filer (4 selskaper, 2022–2026): alle bilag, linjer og beløp importert 0-tap.

Avvik mot den generiske modulen som håndteres her:

1. **Kontokode:** norsk SAF-T fyller `AccountID`, mens `StandardAccountID` er TOM.
   Generisk modul kaller `.text` direkte og krasjer (`AttributeError`). `AccountID` brukes som fallback.

2. **Kontotype:** norsk SAF-T setter `AccountType` = `GL` på ALLE kontoer (ubrukelig for typing).
   `GroupingCategory` (NS 4102) brukes i stedet for presis kontotype.

3. **Analytisk dimensjon:** norsk SAF-T legger Prosjekt/Avdeling i `AnalysisType` `P`/`A`.
   Generisk modul ignorerer `<Analysis>` — her leses de og legges som analytisk distribusjon
   på hver bilagslinje (58 % av linjene har dimensjon; hele grunnen til modulen).

4. **Bilag-ID ikke unik:** PowerOffice gjenbruker `TransactionID` på tvers av OG innen perioder.
   Generisk modul bruker den som xml_id-nøkkel og OVERSKRIVER kolliderende bilag (stille datatap).
   Her gjøres nøkkelen unik med `Period` + løpenummer.

5. **Journal-kode:** POGs `JournalID` er 15-tegns hash (felles prefiks). Odoo `journal.code` er
   maks 5 tegn → kolliderer på tvers av år. Her settes en kort, unik årskode (`SAF<YY>`).

Kompatibilitetsfikser mot Odoo 19 / basemodulen (`account_saft_import`):
- basen setter `res.partner.mobile` (fjernet i Odoo 19) → strippes.
- basens `_prepare_opening_balance_move` returnerer `None` (ikke `{}`) uten balanseforskjell → normaliseres.
    """,
    'depends': [
        'account_saft_import',
        'l10n_no',
    ],
    'data': [],
    'author': 'FIQ',
    # OEEL-1 arves fra account_saft_import (Enterprise) som denne utvider.
    'license': 'OEEL-1',
    'auto_install': False,
}
