import os
from unittest.mock import patch

from odoo.tests import new_test_user
from odoo.tools import config

from odoo.addons.muk_ai.tests.common import AITestCommon

CPF = '12345678909'


class TestTokenStore(AITestCommon):
    def setUp(self):
        super().setUp()
        env = {k: v for k, v in os.environ.items() if k != 'ODOO_AI_PII_KEY'}
        env['ODOO_AI_PII_KEY'] = 'test-key'
        env_patch = patch.dict(os.environ, env, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        options = {k: v for k, v in config.options.items() if k != 'ai_pii_key'}
        conf_patch = patch.dict(config.options, options, clear=True)
        conf_patch.start()
        self.addCleanup(conf_patch.stop)
        self.env['ir.config_parameter'].sudo().set_param('itbr_muk_ai_pii.enabled', 'True')
        self.store = self.env['itbr.muk_ai.pii.token']
        self.user = new_test_user(self.env, login='pii_user_a', groups='base.group_user')
        self.other = new_test_user(self.env, login='pii_user_b', groups='base.group_user')
        self.session = self._session(self.user)

    def _session(self, user):
        return self.env['muk_ai.session'].with_user(user).create({'name': 'PII'}).sudo()

    def test_token_shape(self):
        self.assertRegex(self.store._emit('CPF', CPF, self.session), r'^CPF#[0-9a-f]{12}$')

    def test_deterministic(self):
        first = self.store._emit('CPF', CPF, self.session)
        second = self.store._emit('CPF', CPF, self._session(self.user))
        self.assertEqual(first, second)

    def test_reveal_own(self):
        token = self.store._emit('CPF', CPF, self.session)
        self.assertEqual(self.store._reveal(f'x {token} y', self.session), f'x {CPF} y')

    def test_foreign_token_not_revealed(self):
        token = self.store._emit('CPF', CPF, self._session(self.other))
        self.assertEqual(self.store._reveal(f'x {token}', self.session), f'x {token}')

    def test_unknown_token_literal(self):
        self.assertEqual(
            self.store._reveal('CPF#000000000000', self.session), 'CPF#000000000000'
        )

    def test_disabled_without_key(self):
        del os.environ['ODOO_AI_PII_KEY']
        self.assertFalse(self.store._enabled())
        self.assertEqual(self.store._emit('CPF', CPF, self.session), CPF)

    def test_disabled_by_setting(self):
        self.env['ir.config_parameter'].sudo().set_param('itbr_muk_ai_pii.enabled', False)
        self.assertEqual(self.store._emit('CPF', CPF, self.session), CPF)

    def test_reveal_any_nested(self):
        token = self.store._emit('CPF', CPF, self.session)
        data = {'a': [f'v {token}', 3, None], 'b': {'c': token, 'd': 1.5}}
        self.assertEqual(
            self.store._reveal_any(data, self.session),
            {'a': [f'v {CPF}', 3, None], 'b': {'c': CPF, 'd': 1.5}},
        )
