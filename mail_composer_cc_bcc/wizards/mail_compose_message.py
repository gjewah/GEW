# Copyright 2023 Camptocamp
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import itertools

from odoo import Command, api, fields, models, tools


class MailComposeMessage(models.TransientModel):
    _inherit = "mail.compose.message"

    partner_cc_ids = fields.Many2many(
        "res.partner",
        "mail_compose_message_res_partner_cc_rel",
        "wizard_id",
        "partner_id",
        string="Cc",
        compute="_compute_partner_cc_bcc_ids",
        readonly=False,
        store=True,
    )
    partner_bcc_ids = fields.Many2many(
        "res.partner",
        "mail_compose_message_res_partner_bcc_rel",
        "wizard_id",
        "partner_id",
        string="Bcc",
        compute="_compute_partner_cc_bcc_ids",
        readonly=False,
        store=True,
    )

    # ------------------------------------------------------------
    # SET DEFAULT VALUES FOR CC, BCC
    # ------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        company = self.env.company
        res = super().default_get(fields_list)
        partner_cc = company.default_partner_cc_ids
        if partner_cc:
            res["partner_cc_ids"] = [Command.set(partner_cc.ids)]
        partner_bcc = company.default_partner_bcc_ids
        if partner_bcc:
            res["partner_bcc_ids"] = [Command.set(partner_bcc.ids)]
        return res

    @api.depends(
        "composition_mode", "model", "parent_id", "res_domain", "res_ids", "template_id"
    )
    def _compute_partner_cc_bcc_ids(self):
        for composer in self:
            if (
                composer.template_id
                and composer.composition_mode == "comment"
                and not composer.composition_batch
            ):
                res_ids = composer._evaluate_res_ids() or [0]
                rendered_values = composer._generate_template_for_composer(
                    res_ids,
                    {"email_cc"},
                    allow_suggested=False,
                    find_or_create_partners=False,
                )[res_ids[0]]
                composer._set_partner_ids_from_mails(
                    rendered_values.get("email_cc"), "partner_cc_ids"
                )
                rendered_values = composer._generate_template_for_composer(
                    res_ids,
                    {"email_bcc"},
                    allow_suggested=False,
                    find_or_create_partners=False,
                )[res_ids[0]]
                composer._set_partner_ids_from_mails(
                    rendered_values.get("email_bcc"), "partner_bcc_ids"
                )
            elif composer.parent_id and composer.composition_mode == "comment":
                composer.partner_cc_ids = composer.parent_id.partner_cc_ids
                composer.partner_bcc_ids = composer.parent_id.partner_bcc_ids
            elif not composer.template_id:
                composer.partner_cc_ids = self.env.company.default_partner_cc_ids
                composer.partner_bcc_ids = self.env.company.default_partner_bcc_ids

    @api.depends(
        "composition_mode",
        "model",
        "parent_id",
        "res_domain",
        "res_ids",
        "subtype_id",
        "template_id",
    )
    def _compute_partner_ids(self):
        """Change from Odoo native: do NOT add email_cc to partner_ids.

        Re-derived 2026-07-25 from odoo/addons/mail/wizard/mail_compose_message.py
        (19.0, _compute_partner_ids) so the ONLY difference from upstream is the
        omitted "email_cc" field. The upstream-hash canary test caught that this
        copy had drifted three ways behind Odoo 19: a missing "subtype_id"
        dependency, a missing use_default_to guard, and a hardcoded
        allow_suggested=False.
        """
        for composer in self:
            template = composer.template_id
            # Use template in comment mode only if there are no partners yet or if
            # the template specifies different ones, as suggested recipients should
            # normally not change and we do not want to re-add them every time.
            if (
                template
                and composer.composition_mode == "comment"
                and not composer.composition_batch
                and (not template.use_default_to or not composer.partner_ids)
            ):
                res_ids = composer._evaluate_res_ids() or [0]
                rendered_values = composer._generate_template_for_composer(
                    res_ids,
                    # DIFFERENT FROM ODOO NATIVE: "email_cc" is intentionally
                    # omitted — that is the whole purpose of this module.
                    {"email_to", "partner_ids"},
                    allow_suggested=composer.message_type == "comment"
                    and not composer.subtype_is_log,
                    find_or_create_partners=True,
                )[res_ids[0]]
                if rendered_values.get("partner_ids"):
                    composer.partner_ids = rendered_values["partner_ids"]
            elif composer.parent_id and composer.composition_mode == "comment":
                composer.partner_ids = composer.parent_id.partner_ids
            elif not composer.template_id:
                composer.partner_ids = False

    def _set_partner_ids_from_mails(self, email_field, partner_field):
        if email_field:
            mails = tools.email_split(email_field)
            partner_ids = self.env["res.partner"]._find_or_create_from_emails(
                mails,
                additional_values={
                    email: {
                        "company_id": self.record_company_id.id,
                    }
                    for email in itertools.chain(mails, [False])
                },
            )
            if not isinstance(partner_ids, list):
                partner_ids = [partner_ids]
            for partner_id in partner_ids:
                setattr(self, partner_field, [(4, partner_id.id)])

    # ------------------------------------------------------------
    # RENDERING / VALUES GENERATION
    # ------------------------------------------------------------

    def _prepare_mail_values_rendered(self, res_ids):
        """
        add cc and bcc when send to mail.message
        """
        mail_values = super()._prepare_mail_values_rendered(res_ids)

        for res_id in mail_values:
            mail_values[res_id].update(
                {
                    "recipient_cc_ids": self.partner_cc_ids.ids,
                    "recipient_bcc_ids": self.partner_bcc_ids.ids,
                }
            )
        return mail_values

    # ------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------

    def _action_send_mail_comment(self, res_ids):
        """Add context is_from_composer"""
        self.ensure_one()
        context = {
            "is_from_composer": True,
            "partner_cc_ids": self.partner_cc_ids,
            "partner_bcc_ids": self.partner_bcc_ids,
        }
        self = self.with_context(**context)
        return super()._action_send_mail_comment(res_ids)
