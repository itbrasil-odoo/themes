from __future__ import annotations

from unittest.mock import patch

import requests

from odoo.exceptions import UserError

from odoo.addons.muk_ai.providers.anthropic import AnthropicProvider
from odoo.addons.muk_ai.tests.common import AITestCommon

KEY = 'sk-ant-api03-SECRETSECRETSECRET'


class TestProviderSecrets(AITestCommon):
    """Verify the API key is resolved through the provider and never leaks."""

    def setUp(self) -> None:
        super().setUp()
        self.provider_anthropic.api_key = KEY

    def test_client_reads_the_key_through_the_provider_hook(self):
        client = self.provider_anthropic._get_client()
        with patch.object(
            type(self.provider_anthropic),
            '_resolve_api_key',
            autospec=True,
            return_value='from-hook',
        ):
            self.assertEqual(client.api_key, 'from-hook')
            self.assertTrue(client.authenticated)

    def test_mask_secrets_hides_the_literal_key_and_known_prefixes(self):
        text = (
            f'bad header {KEY} and AIzaSyA1234567890abcdefghijklmnop '
            'and sk-proj-abcdefghijklmnop1234 end'
        )
        masked = self.provider_anthropic._mask_secrets(text)
        self.assertNotIn('SECRETSECRET', masked)
        self.assertNotIn('AIzaSyA1234567890', masked)
        self.assertNotIn('sk-proj-abcdefghijklmnop', masked)
        self.assertIn('bad header', masked)
        self.assertIn('end', masked)

    def test_transport_error_carrying_the_key_is_masked(self):
        client = self.provider_anthropic._get_client()
        error = requests.exceptions.InvalidHeader(
            f'Invalid leading whitespace in header value: {KEY}\n'
        )
        with (
            patch.object(
                AnthropicProvider, '_http_session', autospec=True
            ) as session,
            self.assertRaises(UserError) as caught,
        ):
            session.return_value.post.side_effect = error
            client._post_json('/messages', {})
        self.assertNotIn('SECRETSECRET', str(caught.exception))
        self.assertNotIn('SECRETSECRET', repr(caught.exception.args))
