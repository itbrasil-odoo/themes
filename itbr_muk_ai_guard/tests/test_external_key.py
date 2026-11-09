import os
from unittest.mock import patch

from odoo.tools import config

from odoo.addons.muk_ai.tests.common import AITestCommon

ENV_KEY = 'sk-ant-from-environment-0001'
CONF_KEY = 'sk-ant-from-odoo-conf-00002'
DB_KEY = 'sk-ant-from-the-database-03'


class TestExternalKey(AITestCommon):
    def setUp(self):
        super().setUp()
        self.provider = self.provider_anthropic
        self.provider.api_key = False
        env = {k: v for k, v in os.environ.items() if not k.startswith('ODOO_AI_KEY_')}
        self.env_patch = patch.dict(os.environ, env, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        options = {k: v for k, v in config.options.items() if not k.startswith('ai_key_')}
        self.conf_patch = patch.dict(config.options, options, clear=True)
        self.conf_patch.start()
        self.addCleanup(self.conf_patch.stop)

    def _client_key(self):
        return self.provider._get_client().api_key

    def test_environment_variable(self):
        os.environ['ODOO_AI_KEY_ANTHROPIC'] = ENV_KEY
        self.assertEqual(self._client_key(), ENV_KEY)
        self.assertTrue(self.provider.api_key_external)

    def test_odoo_conf_option(self):
        config.options['ai_key_anthropic'] = CONF_KEY
        self.assertEqual(self._client_key(), CONF_KEY)
        self.assertTrue(self.provider.api_key_external)

    def test_environment_wins_over_odoo_conf(self):
        os.environ['ODOO_AI_KEY_ANTHROPIC'] = ENV_KEY
        config.options['ai_key_anthropic'] = CONF_KEY
        self.assertEqual(self._client_key(), ENV_KEY)

    def test_account_specific_name_wins(self):
        self.provider.code = 'Filial 2'
        os.environ['ODOO_AI_KEY_ANTHROPIC'] = ENV_KEY
        config.options['ai_key_anthropic_filial_2'] = CONF_KEY
        self.assertEqual(self._client_key(), CONF_KEY)
        os.environ['ODOO_AI_KEY_ANTHROPIC_FILIAL_2'] = 'sk-ant-specific-env-000004'
        self.assertEqual(self._client_key(), 'sk-ant-specific-env-000004')

    def test_value_is_stripped(self):
        os.environ['ODOO_AI_KEY_ANTHROPIC'] = f'  {ENV_KEY}\n'
        self.assertEqual(self._client_key(), ENV_KEY)

    def test_database_is_the_fallback(self):
        self.provider.api_key = DB_KEY
        self.assertEqual(self._client_key(), DB_KEY)
        self.assertFalse(self.provider.api_key_external)

    def test_no_key_anywhere(self):
        self.assertFalse(self.provider._get_client().authenticated)
        self.assertFalse(self.provider.api_key_external)

    def test_server_key_wins_over_database_with_a_warning(self):
        self.provider.api_key = DB_KEY
        os.environ['ODOO_AI_KEY_ANTHROPIC'] = ENV_KEY
        with self.assertLogs(
            'odoo.addons.itbr_muk_ai_guard.models.muk_ai_provider', 'WARNING'
        ) as logs:
            self.assertEqual(self._client_key(), ENV_KEY)
        output = '\n'.join(logs.output)
        self.assertNotIn(ENV_KEY, output)
        self.assertNotIn(DB_KEY, output)

    def test_external_key_is_masked_in_errors(self):
        os.environ['ODOO_AI_KEY_ANTHROPIC'] = ENV_KEY
        masked = self.provider._mask_secrets(f'header {ENV_KEY}')
        self.assertNotIn('from-environment', masked)
