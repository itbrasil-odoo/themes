import logging
import os
import re

from odoo import api, fields, models
from odoo.tools import config

_logger = logging.getLogger(__name__)

# Providers already warned about a key kept in the database as well, so the
# warning shows once per process instead of on every request.
_WARNED = set()


def account_suffix(code):
    """Return the account part of the key name: upper case, ``[A-Z0-9_]``."""
    return re.sub(r'[^A-Z0-9]', '_', code.upper())


class MukAIProvider(models.Model):
    _inherit = 'muk_ai.provider'

    api_key_external = fields.Boolean(
        compute='_compute_api_key_external',
        string='Key set on the server',
        help=(
            'The API key comes from the ODOO_AI_KEY_<PROVIDER> environment '
            'variable or the ai_key_<provider> option of the Odoo configuration '
            'file, not from the database.'
        ),
    )

    def _external_key_names(self):
        """Return the key names to look up, the account-specific one first."""
        self.ensure_one()
        names = [(self.name or '').upper()]
        if self.code and self.code != 'default':
            names.insert(0, f'{names[0]}_{account_suffix(self.code)}')
        return names

    def _external_api_key(self):
        """Return the key from the environment or the Odoo configuration file."""
        for name in self._external_key_names():
            value = os.environ.get(f'ODOO_AI_KEY_{name}') or config.get(
                f'ai_key_{name.lower()}'
            )
            if value and (value := str(value).strip()):
                return value
        return ''

    def _resolve_api_key(self):
        if key := self._external_api_key():
            if self.sudo().api_key and self.id not in _WARNED:
                _WARNED.add(self.id)
                _logger.warning(
                    'AI provider %s has an API key on the server and another one '
                    'in the database; the server one is used. Clear the one in '
                    'the database.',
                    self.display_name,
                )
            return key
        return super()._resolve_api_key()

    @api.depends('name', 'code')
    def _compute_api_key_external(self):
        for record in self:
            record.api_key_external = bool(record.name and record._external_api_key())
