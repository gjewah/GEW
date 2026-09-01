# Copyright 2026
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
# 🔴 IKKE SLETT DENNE MODULMAPPEN uten å avinstallere modulen på Production FØRST.
# Historikk (01.09.2026, AI PK): commit 1379497 slettet mappen 31.08 for å fjerne
# 2 res.company-warnings på fiqas Staging (der modulen alt var avinstallert). Men
# fiqas Production hadde modulen state=installed. Da Staging→Production ble merget,
# fant Production-`-u` en installert modul uten kode på disk → «not installable,
# skipped» → «ERROR: Some modules are not loaded» → bygget feilet → rollback →
# fiqas Production 500 i mange timer. Vi har ikke Production-DB-tilgang, så den
# eneste git-veien tilbake er å GJENINNFØRE modulen (denne mappen). Skal den bort
# for godt: bygg Kartverket-erstatningen, avinstaller på Production via en
# migrering, og fjern DERETTER mappen. Samme feilform som SDV partner_firstname.
{
    "name": "Store Company Addresses",
    "summary": "Align res.company address compute fields across base_location and res_company_search_view",
    "version": "19.0.1.2.2",
    "author": "FIQ, Loym",
    "license": "AGPL-3",
    "depends": ["base_location", "res_company_search_view"],
    "data": [],
    "installable": True,
}
