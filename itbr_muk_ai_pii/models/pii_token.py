from odoo import api, fields, models

from ..tools.keys import TOKEN_RE, make_token, pii_key

PARAM_ENABLED = 'itbr_muk_ai_pii.enabled'


class PiiToken(models.Model):
    _name = 'itbr.muk_ai.pii.token'
    _description = 'AI personal data token'
    _log_access = False

    token = fields.Char(required=True, index=True)
    kind = fields.Char(required=True)
    value = fields.Char(required=True)
    session_ids = fields.Many2many(
        'muk_ai.session',
        relation='itbr_muk_ai_pii_token_session_rel',
        column1='token_id',
        column2='session_id',
    )

    _token_unique = models.Constraint('unique(token)', 'The token must be unique.')

    @api.model
    def _enabled(self):
        return bool(pii_key()) and (
            self.env['ir.config_parameter'].sudo().get_param(PARAM_ENABLED) == 'True'
        )

    @api.model
    def _emit(self, kind, value, session):
        """Return the token for ``value`` and link it to ``session``.

        Returns ``value`` unchanged when tokens are off or there is no session.
        """
        if not session or not self._enabled():
            return value
        token = make_token(kind, value, pii_key())
        # Idempotent insert: two sessions emitting the same new value at once
        # must not trip over the unique constraint.
        self.env.flush_all()
        self.env.cr.execute(
            'INSERT INTO itbr_muk_ai_pii_token (token, kind, value) '
            'VALUES (%s, %s, %s) ON CONFLICT (token) DO NOTHING',
            (token, kind, value),
        )
        self.env.invalidate_all()
        self.sudo().search([('token', '=', token)], limit=1).session_ids = [
            (4, session.id)
        ]
        return token

    @api.model
    def _tree_session_ids(self, session):
        """Return the ids of the sessions in the subagent tree of ``session``."""
        session = session.sudo()
        if 'parent_session_id' not in session._fields:
            return session.ids
        root = session
        seen = set()
        while root.parent_session_id and root.id not in seen:
            seen.add(root.id)
            root = root.parent_session_id
        tree = root
        children = root
        while children:
            children = children.search([('parent_session_id', 'in', children.ids)]) - tree
            tree |= children
        return tree.ids

    @api.model
    def _reveal(self, text, session):
        """Swap the tokens of the user (or subagent tree) for their values."""
        if not text or not session or not isinstance(text, str):
            return text
        found = {m.group(0) for m in TOKEN_RE.finditer(text)}
        if not found:
            return text
        domain = [('session_ids', 'in', self._tree_session_ids(session))]
        if user := session.sudo().user_id:
            domain = ['|', ('session_ids.user_id', '=', user.id)] + domain
        records = self.sudo().search([('token', 'in', list(found))] + domain)
        values = {r.token: r.value for r in records}
        return TOKEN_RE.sub(lambda m: values.get(m.group(0), m.group(0)), text)

    @api.model
    def _reveal_any(self, data, session):
        if isinstance(data, str):
            return self._reveal(data, session)
        if isinstance(data, dict):
            return {k: self._reveal_any(v, session) for k, v in data.items()}
        if isinstance(data, list):
            return [self._reveal_any(v, session) for v in data]
        return data
