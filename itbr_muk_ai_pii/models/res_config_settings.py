from odoo import api, fields, models

from ..tools.keys import pii_key


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    itbr_muk_ai_pii_enabled = fields.Boolean(
        string='Protect personal data',
        config_parameter='itbr_muk_ai_pii.enabled',
    )
    itbr_muk_ai_pii_key_set = fields.Boolean(
        string='Key set on the server',
        compute='_compute_itbr_muk_ai_pii_key_set',
        readonly=True,
    )
    itbr_muk_ai_pii_blocked_models = fields.Char(
        string='Blocked models',
        config_parameter='itbr_muk_ai_pii.blocked_models',
    )
    itbr_muk_ai_pii_email_domains = fields.Char(
        string='Company e-mail domains',
        config_parameter='itbr_muk_ai_pii.email_domains',
    )

    @api.depends_context('uid')
    def _compute_itbr_muk_ai_pii_key_set(self):
        key_set = bool(pii_key())
        for record in self:
            record.itbr_muk_ai_pii_key_set = key_set
