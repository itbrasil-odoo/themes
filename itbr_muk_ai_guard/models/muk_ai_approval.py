from odoo import api, models

from .res_config_settings import APPROVE_ALL_WRITES, guard_enabled


class MukAIApproval(models.Model):
    _inherit = 'muk_ai.approval'

    @api.model
    def _is_sensitive_model(self, model_name):
        """Treat every model as sensitive while approving every write is on."""
        return guard_enabled(self.env, APPROVE_ALL_WRITES) or super()._is_sensitive_model(
            model_name
        )
