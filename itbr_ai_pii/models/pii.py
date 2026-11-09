from odoo import api, models

# The token store holds real values, so no tool may reach it
ALWAYS_BLOCKED_MODELS = frozenset({'itbr.ai.pii.token'})
PARAM_BLOCKED_MODELS = 'itbr_ai_pii.blocked_models'
PARAM_EMAIL_DOMAINS = 'itbr_ai_pii.email_domains'


class ItbrAiPii(models.AbstractModel):
    _name = 'itbr.ai.pii'
    _description = 'AI personal data protection (facade)'

    @api.model
    def _csv_param(self, key):
        value = self.env['ir.config_parameter'].sudo().get_str(key, '')
        return {item.strip() for item in (value or '').split(',') if item.strip()}

    @api.model
    def _blocked_models(self):
        """Return the blocked model names that exist in this registry."""
        names = self._csv_param(PARAM_BLOCKED_MODELS) | ALWAYS_BLOCKED_MODELS
        return frozenset(name for name in names if name in self.env)

    @api.model
    def _is_blocked(self, model_name):
        return model_name in self._blocked_models()

    @api.model
    def _field_level(self, model_name, field_name):
        """Return 'allow', 'tokenize' or 'block'; a relation to a blocked model blocks."""
        field = self.env[model_name]._fields.get(field_name) if model_name in self.env else None
        if field is not None and field.relational and field.comodel_name in self._blocked_models():
            return 'block'
        return self.env['ir.model.fields']._ai_exposure_map(model_name).get(field_name, 'allow')

    @api.model
    def _email_domains(self):
        return frozenset(domain.lower().lstrip('@') for domain in self._csv_param(PARAM_EMAIL_DOMAINS))

    @api.model
    def _tokens_available(self):
        return self.env['itbr.ai.pii.token']._enabled()
