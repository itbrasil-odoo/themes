from odoo import _, api, models
from odoo.exceptions import AccessError


class MCPMixin(models.AbstractModel):
    """Keep whole models (HR/payroll, bank data) out of reach of the AI."""

    _inherit = 'muk_mcp.mixin'

    @api.model
    def _itbr_pii_blocked_models(self):
        """Return the blocked model names that exist in this registry."""
        value = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('itbr_muk_ai_pii.blocked_models', '')
        )
        names = {name.strip() for name in (value or '').split(',') if name.strip()}
        return frozenset(name for name in names if name in self.env)

    @api.model
    def _resolve_model(self, model):
        if model in self._itbr_pii_blocked_models():
            raise AccessError(
                _('Model %(model)r is not accessible via MCP.', model=model)
            )
        return super()._resolve_model(model)

    @api.model
    def _mcp_listable_model_names(self):
        listable = super()._mcp_listable_model_names()
        if listable is None:
            listable = set(self.env.registry)
        return set(listable) - self._itbr_pii_blocked_models()

    @api.model
    def _mcp_record_domain(self, model):
        """Hide records attached to a blocked model from attachment/message models."""
        domain = super()._mcp_record_domain(model)
        if model not in ('ir.attachment', 'mail.message', 'mail.activity'):
            return domain
        blocked = self._itbr_pii_blocked_models()
        if not blocked:
            return domain
        extra = [('res_model', 'not in', sorted(blocked))]
        if model == 'mail.message':
            extra = [('model', 'not in', sorted(blocked))]
        return list(domain) + extra if domain else extra
