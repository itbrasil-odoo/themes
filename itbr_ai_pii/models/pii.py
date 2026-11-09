import re

from odoo import api, models

from ..tools.detector import tokenize_text
from ..tools.keys import TOKEN_RE
from ..tools.records import Masker

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

    @api.model
    def _masker(self, external=False):
        """Return a :class:`Masker` of tool results for the current user."""
        return Masker(self.env, external=external)

    @api.model
    def _mask_text(self, text):
        """Mask personal data of free ``text`` with the current user's tokens.

        Values the user already holds a token for (names, addresses, documents,
        dates) are swapped back to that token, whole words only and longest
        first; then CPF, CNPJ, e-mail and phone are detected. Same input, same
        output. Without tokens the text is returned as it is.
        """
        if not text or not isinstance(text, str) or not self._tokens_available():
            return text
        store = self.env['itbr.ai.pii.token']
        known = {}
        for value, token in store._known_in(text):
            known.setdefault(value, token)
        if known:
            # one pass: existing tokens are kept, a value is never matched
            # inside a token, nor inside a longer value already replaced
            pattern = re.compile(
                '(?P<token>' + TOKEN_RE.pattern + ')|(?<!\\w)(?:'
                + '|'.join(re.escape(value) for value in known)
                + ')(?!\\w)'
            )
            used = set()

            def remask(match):
                if match.group('token'):
                    return match.group(0)
                used.add(known[match.group(0)])
                return known[match.group(0)]

            text = pattern.sub(remask, text)
            store._touch(sorted(used))
        return tokenize_text(text, store._emit, self._email_domains())

    @api.model
    def _mask_any(self, data):
        """Apply :meth:`_mask_text` to every string of nested dicts and lists."""
        if isinstance(data, str):
            return self._mask_text(data)
        if isinstance(data, dict):
            return {key: self._mask_any(value) for key, value in data.items()}
        if isinstance(data, list):
            return [self._mask_any(value) for value in data]
        return data
