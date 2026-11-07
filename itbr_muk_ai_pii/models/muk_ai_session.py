from odoo import models


class MukAiSession(models.Model):
    _inherit = 'muk_ai.session'

    def _tool_dispatch_context(self):
        """Tell tool results which chat they go to, so they can be tokenized for it."""
        return {**super()._tool_dispatch_context(), 'itbr_pii_session_id': self.id}
