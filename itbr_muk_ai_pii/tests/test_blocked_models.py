import json

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestBlockedModels(TransactionCase):
    def _call(self, name, arguments):
        return self.env['muk_mcp.tool']._call(name, arguments, self.env)

    def _set_blocked(self, value):
        self.env['ir.config_parameter'].sudo().set_param(
            'itbr_muk_ai_pii.blocked_models', value
        )

    def test_blocked_model_refused(self):
        with self.assertRaises(AccessError):
            self._call('search_read', {'model': 'res.partner.bank'})

    def test_error_text_matches_access_module(self):
        with self.assertRaises(AccessError) as cm:
            self._call('search_read', {'model': 'res.partner.bank'})
        self.assertIn(
            "Model 'res.partner.bank' is not accessible via MCP.", str(cm.exception)
        )

    def test_list_models_hides_blocked(self):
        text, _info = self._call('list_models', {'search': 'res.partner', 'limit': 500})
        names = {row['model'] for row in json.loads(text)}
        self.assertIn('res.partner', names)
        self.assertNotIn('res.partner.bank', names)

    def test_unblocking_makes_readable(self):
        self._set_blocked('hr.payslip')
        self._call('search_read', {'model': 'res.partner.bank'})
        text, _info = self._call('list_models', {'search': 'res.partner.bank'})
        self.assertIn('res.partner.bank', {r['model'] for r in json.loads(text)})

    def test_unknown_names_ignored(self):
        self._set_blocked('no.such.model, res.partner.bank')
        blocked = self.env['muk_mcp.mixin']._itbr_pii_blocked_models()
        self.assertEqual(blocked, frozenset({'res.partner.bank'}))
