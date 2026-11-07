from odoo import fields, models

APPROVE_ALL_WRITES = 'itbr_muk_ai_guard.approve_all_writes'
ADMIN_ONLY_APPROVAL_OFF = 'itbr_muk_ai_guard.admin_only_approval_off'
BLOCK_WEB = 'itbr_muk_ai_guard.block_web'


def guard_enabled(env, key):
    """Return whether the guard ``key`` is switched on.

    Installation writes every key as ``True``; unticking it in the settings
    removes the parameter, which reads as off.
    """
    return env['ir.config_parameter'].sudo().get_param(key) == 'True'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    itbr_muk_ai_guard_approve_all_writes = fields.Boolean(
        string='Approve every write',
        config_parameter=APPROVE_ALL_WRITES,
    )
    itbr_muk_ai_guard_admin_only_approval_off = fields.Boolean(
        string='Only admins turn approvals off',
        config_parameter=ADMIN_ONLY_APPROVAL_OFF,
    )
    itbr_muk_ai_guard_block_web = fields.Boolean(
        string='Block web access',
        config_parameter=BLOCK_WEB,
    )
