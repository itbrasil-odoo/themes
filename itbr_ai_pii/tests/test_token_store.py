import os
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged



@tagged('post_install', '-at_install')
class TestTokenStore(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = cls.env['res.users'].create(
            {'name': 'A', 'login': 'pii_a', 'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])]}
        )
        cls.user_b = cls.env['res.users'].create(
            {'name': 'B', 'login': 'pii_b', 'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])]}
        )
        cls.Token = cls.env['itbr.ai.pii.token']

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {'ODOO_AI_PII_KEY': 'k'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_emit_is_deterministic_and_idempotent(self):
        first = self.Token._emit('CPF', '52998224725')
        second = self.Token._emit('CPF', '52998224725')
        self.assertEqual(first, second)
        self.assertRegex(first, r'^CPF#[0-9a-f]{12}$')
        self.assertEqual(self.Token.sudo().search_count([('token', '=', first)]), 1)

    def test_reveal_only_to_emitting_user(self):
        token = self.Token.with_user(self.user_a)._emit('CPF', '52998224725')
        self.assertIn('52998224725', self.Token.with_user(self.user_a)._reveal(f'x {token}'))
        self.assertEqual(self.Token.with_user(self.user_b)._reveal(f'x {token}'), f'x {token}')

    def test_reveal_leaves_unknown_tokens(self):
        text = 'x CPF#000000000000 y'
        self.assertEqual(self.Token._reveal(text), text)

    def test_reveal_any_walks_dicts_and_lists(self):
        token = self.Token._emit('CPF', '52998224725')
        data = {'a': [f'{token}', {'b': token}], 'n': 3}
        self.assertEqual(
            self.Token._reveal_any(data),
            {'a': ['52998224725', {'b': '52998224725'}], 'n': 3},
        )

    def test_known_in_returns_longest_first(self):
        short = self.Token._emit('NAME', 'Ana')
        long = self.Token._emit('NAME', 'Ana Maria')
        self.assertEqual(
            self.Token._known_in('Ana Maria pagou'),
            [('Ana Maria', long), ('Ana', short)],
        )
        self.assertEqual(self.Token.with_user(self.user_b)._known_in('Ana Maria pagou'), [])

    def test_disabled_without_key(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('ODOO_AI_PII_KEY', None)
            with patch('odoo.addons.itbr_ai_pii.models.pii_token.pii_key', return_value=''):
                before = self.Token.sudo().search_count([])
                self.assertEqual(self.Token._emit('CPF', '52998224725'), '52998224725')
                self.assertEqual(self.Token.sudo().search_count([]), before)

    def test_gc_removes_expired_only(self):
        now = fields.Datetime.now()
        old = self.Token.sudo().create(
            {'token': 'CPF#aaaaaaaaaaaa', 'kind': 'CPF', 'value': 'a', 'last_emitted': now - timedelta(days=31)}
        )
        fresh = self.Token.sudo().create(
            {'token': 'CPF#bbbbbbbbbbbb', 'kind': 'CPF', 'value': 'b', 'last_emitted': now - timedelta(days=29)}
        )
        self.Token._gc_expired()
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    def test_token_table_not_readable_by_user(self):
        with self.assertRaises(AccessError):
            self.Token.with_user(self.user_a).search([])
