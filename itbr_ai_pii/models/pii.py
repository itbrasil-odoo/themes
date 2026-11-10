import re

from odoo import api, models

from ..tools.detector import tokenize_text
from ..tools.keys import TOKEN_RE
from ..tools.records import Masker

# The token store holds real values, so no tool may reach it
ALWAYS_BLOCKED_MODELS = frozenset({'itbr.ai.pii.token'})
PARAM_BLOCKED_MODELS = 'itbr_ai_pii.blocked_models'
PARAM_EMAIL_DOMAINS = 'itbr_ai_pii.email_domains'


def _known_pattern(value, token):
    """Regex of a value already emitted as ``token``, as a whole word.

    Words may be split by any run of whitespace. An e-mail must not be the
    tail of a longer address; other kinds (digits included) must not touch
    another word character.
    """
    body = r'\s+'.join(re.escape(word) for word in value.split())
    if token.startswith('EMAIL#'):
        return r'(?<![\w.+-])' + body + r'(?![\w-])'
    return r'(?<!\w)' + body + r'(?!\w)'


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
    def _masker(self, external=False, redact_persons=False):
        """Return a :class:`Masker` of tool results for the current user.

        ``redact_persons`` (external only): person names become ``[removido]``.
        """
        return Masker(self.env, external=external, redact_persons=redact_persons)

    @api.model
    def _mask_text(self, text, seen=None):
        """Mask personal data of free ``text`` with the current user's tokens.

        Values the user already holds a token for (any kind: a revealed phone
        or CPF comes back as bare digits the detector would miss) are swapped
        back to that token, whole words only, ignoring case
        and runs of whitespace, longest first; then CPF, CNPJ, e-mail and phone
        are detected. Same input, same output. Without tokens the text is
        returned as it is.

        No write happens for the swapped values: their tokens are added to
        ``seen`` (when given) and the caller renews them once with
        ``itbr.ai.pii.token._touch(seen)``. Newly detected values are emitted,
        which already renews them.
        """
        if not text or not isinstance(text, str) or not self._tokens_available():
            return text
        store = self.env['itbr.ai.pii.token']
        # _known_in orders by length desc, so the alternation tries the
        # longest value first at each position
        known = store._known_in(text)
        if known:
            # one pass: existing tokens are kept and never matched inside
            pattern = re.compile(
                '(?P<token>' + TOKEN_RE.pattern + ')|' + '|'.join(
                    f'(?P<v{index}>' + _known_pattern(value, token) + ')'
                    for index, (value, token) in enumerate(known)
                ),
                re.IGNORECASE,
            )

            def remask(match):
                if match.group('token'):
                    return match.group(0)
                token = known[int(match.lastgroup[1:])][1]
                if seen is not None:
                    seen.add(token)
                return token

            text = pattern.sub(remask, text)
        return tokenize_text(text, store._emit, self._email_domains())

    @api.model
    def _mask_any(self, data, touch=True, seen=None):
        """Apply :meth:`_mask_text` to every string of nested dicts and lists.

        With ``touch`` the swapped tokens are renewed once at the end.
        """
        seen = set() if seen is None else seen
        result = self._mask_walk(data, seen)
        if touch and seen:
            self.env['itbr.ai.pii.token']._touch(sorted(seen))
        return result

    @api.model
    def _mask_walk(self, data, seen):
        if isinstance(data, str):
            return self._mask_text(data, seen=seen)
        if isinstance(data, dict):
            return {key: self._mask_walk(value, seen) for key, value in data.items()}
        if isinstance(data, list):
            return [self._mask_walk(value, seen) for value in data]
        return data
