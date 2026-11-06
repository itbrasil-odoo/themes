from __future__ import annotations

from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError

from odoo.addons.muk_ai.providers.anthropic import AnthropicProvider
from odoo.addons.muk_ai.tests.common import AITestCommon

EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')


def api_model(model_id, name, context=1_000_000, efforts=EFFORTS):
    """Build one entry of the Anthropic ``GET /v1/models`` response."""
    effort = {'supported': bool(efforts)}
    effort.update({level: {'supported': level in efforts} for level in EFFORTS})
    return {
        'type': 'model',
        'id': model_id,
        'display_name': name,
        'created_at': '2026-11-01T00:00:00Z',
        'max_input_tokens': context,
        'max_tokens': 128000,
        'capabilities': {'effort': effort},
    }


class TestModelSync(AITestCommon):
    """Verify the model catalogue sync from the provider's model listing."""

    def setUp(self) -> None:
        super().setUp()
        self.provider_anthropic.api_key = 'test-key'
        self.Model = self.env['muk_ai.model'].with_context(active_test=False)

    def _sync(self, pages):
        """Run the sync with ``pages`` served as consecutive model list pages."""
        with patch.object(
            AnthropicProvider, '_get_json', autospec=True, side_effect=pages
        ) as get_json:
            action = self.provider_anthropic.action_sync_models()
        return action, get_json

    def _page(self, *items, has_more=False):
        return {
            'data': list(items),
            'has_more': has_more,
            'first_id': items[0]['id'] if items else None,
            'last_id': items[-1]['id'] if items else None,
        }

    def test_anthropic_maps_the_model_listing(self):
        client = self.provider_anthropic._get_client()
        with patch.object(
            AnthropicProvider,
            '_get_json',
            autospec=True,
            return_value=self._page(
                api_model('claude-new-9', 'Claude New 9', 500_000, ('low', 'high'))
            ),
        ):
            entries = client.list_models()
        self.assertEqual(
            entries,
            [
                {
                    'technical_name': 'claude-new-9',
                    'name': 'Claude New 9',
                    'context_window': 500_000,
                    'reasoning_efforts': ['low', 'high'],
                }
            ],
        )

    def test_listing_follows_pagination(self):
        _action, get_json = self._sync(
            [
                self._page(api_model('claude-new-9', 'Claude New 9'), has_more=True),
                self._page(api_model('claude-new-10', 'Claude New 10')),
            ]
        )
        self.assertEqual(get_json.call_count, 2)
        second_params = get_json.call_args_list[1].args[2]
        self.assertEqual(second_params.get('after_id'), 'claude-new-9')
        self.assertEqual(
            len(self.Model.search([('technical_name', 'in', ['claude-new-9', 'claude-new-10'])])),
            2,
        )

    def test_new_model_is_created_inactive_without_price(self):
        self._sync([self._page(api_model('claude-new-9', 'Claude New 9', 400_000))])
        model = self.Model.search([('technical_name', '=', 'claude-new-9')])
        self.assertTrue(model)
        self.assertFalse(model.active)
        self.assertTrue(model.api_synced)
        self.assertEqual(model.provider_id, self.provider_anthropic)
        self.assertEqual(model.modality, 'chat')
        self.assertEqual(model.context_window, 400_000)
        self.assertEqual(model.reasoning_efforts, list(EFFORTS))
        self.assertEqual(model.input_rate, 0.0)
        self.assertTrue(model.notes)

    def test_synced_model_cannot_be_activated_without_price(self):
        self._sync([self._page(api_model('claude-new-9', 'Claude New 9'))])
        model = self.Model.search([('technical_name', '=', 'claude-new-9')])
        with self.assertRaises(ValidationError):
            model.active = True
        model.write({'input_rate': 1.0, 'output_rate': 5.0, 'active': True})
        self.assertTrue(model.active)

    def test_existing_model_is_not_overwritten(self):
        sonnet = self.env.ref('muk_ai.model_claude_sonnet_5')
        before = sonnet.read(
            ['name', 'context_window', 'reasoning_efforts', 'input_rate', 'active']
        )
        self._sync(
            [self._page(api_model('claude-sonnet-5', 'Renamed', 42_000, ('low',)))]
        )
        self.assertEqual(
            sonnet.read(
                ['name', 'context_window', 'reasoning_efforts', 'input_rate', 'active']
            ),
            before,
        )
        self.assertEqual(
            self.Model.search_count([('technical_name', '=', 'claude-sonnet-5')]), 1
        )

    def test_dated_snapshot_matches_its_alias(self):
        self._sync([self._page(api_model('claude-haiku-4-5-20251001', 'Claude Haiku 4.5'))])
        self.assertFalse(
            self.Model.search([('technical_name', '=', 'claude-haiku-4-5-20251001')])
        )

    def test_sync_reports_what_it_created(self):
        action, _get_json = self._sync(
            [
                self._page(
                    api_model('claude-new-9', 'Claude New 9'),
                    api_model('claude-sonnet-5', 'Claude Sonnet 5'),
                )
            ]
        )
        self.assertEqual(action['tag'], 'display_notification')
        self.assertIn('Claude New 9', action['params']['message'])

    def test_provider_without_listing_refuses(self):
        self.assertTrue(self.provider_anthropic.supports_model_listing)
        provider = self.env.ref('muk_ai.provider_google')
        if provider.supports_model_listing:
            self.skipTest('Google lists models in this build')
        provider.api_key = 'test-key'
        with self.assertRaises(UserError):
            provider.action_sync_models()
