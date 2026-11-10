from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestBlockedModels(TransactionCase):
    def setUp(self):
        super().setUp()
        self.pii = self.env['itbr.ai.pii']

    def _set(self, key, value):
        self.env['ir.config_parameter'].sudo().set_str(f'itbr_ai_pii.{key}', value)

    def test_default_blocked_models_present_only(self):
        blocked = self.pii._blocked_models()
        self.assertIn('res.partner.bank', blocked)
        self.assertTrue(self.pii._is_blocked('res.partner.bank'))
        self.assertNotIn('hr.payslip.line', blocked - set(self.env.registry))
        self.assertTrue(blocked <= set(self.env.registry))

    def test_unknown_names_ignored(self):
        self._set('blocked_models', 'no.such.model, res.partner.bank')
        self.assertEqual(
            self.pii._blocked_models(),
            frozenset({'res.partner.bank', 'itbr.ai.pii.token'}),
        )

    def test_token_store_always_blocked(self):
        self._set('blocked_models', '')
        self.assertTrue(self.pii._is_blocked('itbr.ai.pii.token'))
        self.assertFalse(self.pii._is_blocked('res.partner.bank'))

    def test_relation_to_blocked_model_is_block(self):
        self.assertEqual(self.pii._field_level('res.partner', 'bank_ids'), 'block')
        self.assertEqual(self.pii._field_level('res.partner', 'city'), 'allow')
        self.assertEqual(self.pii._field_level('res.partner', 'vat'), 'tokenize')
        self.assertEqual(self.pii._field_level('res.partner', 'no_such_field'), 'allow')

    def test_email_domains(self):
        self._set('email_domains', 'Acme.com, foo.org ,')
        self.assertEqual(self.pii._email_domains(), frozenset({'acme.com', 'foo.org'}))
        self._set('email_domains', '')
        self.assertEqual(self.pii._email_domains(), frozenset())

    def test_tokens_available(self):
        self.assertEqual(self.pii._tokens_available(), self.env['itbr.ai.pii.token']._enabled())
