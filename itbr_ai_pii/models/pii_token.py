from datetime import timedelta

from odoo import api, fields, models

from ..tools.keys import TOKEN_RE, make_token, pii_key

PARAM_ENABLED = 'itbr_ai_pii.enabled'
PARAM_TTL_DAYS = 'itbr_ai_pii.token_ttl_days'
DEFAULT_TTL_DAYS = 30


class PiiToken(models.Model):
    _name = 'itbr.ai.pii.token'
    _description = 'AI personal data token'
    _log_access = False

    token = fields.Char(required=True)
    kind = fields.Char(required=True)
    value = fields.Char(required=True)
    user_ids = fields.Many2many(
        'res.users',
        relation='itbr_ai_pii_token_user_rel',
        column1='token_id',
        column2='user_id',
    )
    last_emitted = fields.Datetime(index=True, default=fields.Datetime.now)

    _token_unique = models.Constraint('unique(token)', 'The token must be unique.')

    @api.model
    def _enabled(self):
        return bool(pii_key()) and self.env['ir.config_parameter'].sudo().get_bool(
            PARAM_ENABLED, True
        )

    @api.model
    def _emit(self, kind, normalized):
        """Return the token for ``normalized`` and link it to the current user.

        Returns ``normalized`` unchanged when tokens are off.
        """
        if not normalized or not normalized.strip() or not self._enabled():
            return normalized
        token = make_token(kind, normalized, pii_key())
        cr = self.env.cr
        self.env.flush_all()
        # Idempotent insert. DO UPDATE (not DO NOTHING) so the row id is always
        # returned; a conflicting row invisible to this snapshot raises a
        # serialization error, which Odoo retries.
        cr.execute(
            'INSERT INTO itbr_ai_pii_token (token, kind, value, last_emitted) '
            'VALUES (%s, %s, %s, now() at time zone \'utc\') '
            'ON CONFLICT (token) DO UPDATE SET last_emitted = EXCLUDED.last_emitted '
            'RETURNING id',
            (token, kind, normalized),
        )
        token_id = cr.fetchone()[0]
        cr.execute(
            'INSERT INTO itbr_ai_pii_token_user_rel (token_id, user_id) '
            'VALUES (%s, %s) ON CONFLICT DO NOTHING',
            (token_id, self.env.uid),
        )
        self.env.invalidate_all()
        return token

    @api.model
    def _reveal(self, text):
        """Swap the tokens emitted to the current user for their values."""
        if not text or not isinstance(text, str):
            return text
        found = {m.group(0) for m in TOKEN_RE.finditer(text)}
        if not found:
            return text
        records = self.sudo().search(
            [('token', 'in', list(found)), ('user_ids', 'in', self.env.uid)]
        )
        values = {r.token: r.value for r in records}
        return TOKEN_RE.sub(lambda m: values.get(m.group(0), m.group(0)), text)

    @api.model
    def _reveal_any(self, data):
        if isinstance(data, str):
            return self._reveal(data)
        if isinstance(data, dict):
            return {k: self._reveal_any(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._reveal_any(v) for v in data]
        return data

    @api.model
    def _known_in(self, text, kinds=('NAME', 'ADDR', 'DOC', 'DATE')):
        """Return ``(value, token)`` pairs of the user whose value is in ``text``.

        The match ignores case and runs of whitespace (values are stored with
        single spaces). Case folding is the database's ``lower()``, so on a
        ``C`` ctype database it folds ASCII letters only. Longest value first.
        """
        if not text or not kinds:
            return []
        probe = ' '.join(text.split())
        self.env.flush_all()
        self.env.cr.execute(
            'SELECT t.value, t.token FROM itbr_ai_pii_token t '
            'JOIN itbr_ai_pii_token_user_rel r ON r.token_id = t.id '
            'WHERE r.user_id = %(uid)s AND t.kind IN %(kinds)s '
            'AND length(t.value) > 0 AND strpos(lower(%(text)s), lower(t.value)) > 0 '
            'ORDER BY length(t.value) DESC, t.id',
            {'uid': self.env.uid, 'kinds': tuple(kinds), 'text': probe},
        )
        return [(value, token) for value, token in self.env.cr.fetchall()]

    @api.model
    def _touch(self, tokens):
        """Renew ``last_emitted`` of the current user's ``tokens``."""
        if not tokens:
            return
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE itbr_ai_pii_token t SET last_emitted = now() at time zone \'utc\' '
            'FROM itbr_ai_pii_token_user_rel r '
            'WHERE r.token_id = t.id AND r.user_id = %s AND t.token IN %s',
            (self.env.uid, tuple(tokens)),
        )
        self.env.invalidate_all()

    @api.model
    def _gc_expired(self):
        days = self.env['ir.config_parameter'].sudo().get_int(
            PARAM_TTL_DAYS, DEFAULT_TTL_DAYS
        )
        limit = fields.Datetime.now() - timedelta(days=days)
        self.sudo().search([('last_emitted', '<', limit)]).unlink()
