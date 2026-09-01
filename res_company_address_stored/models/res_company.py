from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # res_company_search_view / base_address_extended make the address searchable
    # by storing the address fields on res.company. Odoo 19 requires every field
    # sharing the same compute method (_compute_address) to be consistent in both
    # 'store' and 'compute_sudo', otherwise the registry emits a UserWarning.
    #
    # _compute_address reads partner_id.sudo() (see base/models/res_company.py),
    # so the whole group is stored AND compute_sudo=True to stay consistent.
    #
    # 🔴 FIKS 2026-07-21 (Gjermund fanget at feilen laa i FIQ-koden, ikke i Odoo):
    # Den forrige versjonen redefinerte feltene med KUN store/compute_sudo — uten
    # compute= og inverse=. I Odoo 19 mister feltet da compute-koblingen sin, og
    # overstyringen slaar IKKE gjennom. Maalt paa fiqas Staging 35222813 mens
    # modulen var INSTALLERT: street..country_id sto fortsatt store=False,
    # compute_sudo=False, og city_id/zip_id fantes ikke paa modellen i det hele
    # tatt. Advarselen overlevde derfor alle tidligere «fikser».
    # compute/inverse MAA gjentas ved redefinering. Navn verifisert mot kilden:
    #   base/models/res_company.py:69-74      (street..country_id)
    #   OCA/partner-contact/base_location/models/res_company.py:23-33 (city_id, zip_id)

    street = fields.Char(
        compute="_compute_address", inverse="_inverse_street",
        store=True, compute_sudo=True,
    )
    street2 = fields.Char(
        compute="_compute_address", inverse="_inverse_street2",
        store=True, compute_sudo=True,
    )
    zip = fields.Char(
        compute="_compute_address", inverse="_inverse_zip",
        store=True, compute_sudo=True,
    )
    city = fields.Char(
        compute="_compute_address", inverse="_inverse_city",
        store=True, compute_sudo=True,
    )
    state_id = fields.Many2one(
        "res.country.state",
        compute="_compute_address", inverse="_inverse_state",
        store=True, compute_sudo=True,
    )
    country_id = fields.Many2one(
        "res.country",
        compute="_compute_address", inverse="_inverse_country",
        store=True, compute_sudo=True,
    )
    city_id = fields.Many2one(
        "res.city",
        compute="_compute_address", inverse="_inverse_city_id",
        store=True, compute_sudo=True,
    )
    zip_id = fields.Many2one(
        "res.city.zip",
        compute="_compute_address", inverse="_inverse_zip_id",
        store=True, compute_sudo=True,
    )
