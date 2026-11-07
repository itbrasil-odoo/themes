import json
import os
from unittest.mock import patch

from odoo.tests import new_test_user
from odoo.tools import config

from odoo.addons.muk_ai.tests.common import AITestCommon

from ..tools.keys import make_token

KEY = 'test-key'
CPF = '12345678909'
EMAIL = 'joao@cliente.com.br'


def tok(kind, value):
    return make_token(kind, value, KEY)


class TestReturnPath(AITestCommon):
    def setUp(self):
        super().setUp()
        env = {k: v for k, v in os.environ.items() if k != 'ODOO_AI_PII_KEY'}
        env['ODOO_AI_PII_KEY'] = KEY
        env_patch = patch.dict(os.environ, env, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        options = {k: v for k, v in config.options.items() if k != 'ai_pii_key'}
        conf_patch = patch.dict(config.options, options, clear=True)
        conf_patch.start()
        self.addCleanup(conf_patch.stop)
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('itbr_muk_ai_pii.enabled', 'True')
        params.set_param('itbr_muk_ai_pii.email_domains', '')
        self.user = new_test_user(
            self.env, login='pii_ret_user', name='Vera Vendedora',
            groups='base.group_user,base.group_partner_manager',
        )
        self.session = self.env['muk_ai.session'].with_user(self.user).create({'name': 'PII'})
        store = self.env['itbr.muk_ai.pii.token']
        self.cpf_tok = store._emit('CPF', CPF, self.session.sudo())
        self.email_tok = store._emit('EMAIL', EMAIL, self.session.sudo())
        self.assertEqual(self.cpf_tok, tok('CPF', CPF))

    # ------------------------------------------------------------------
    def _text(self, text):
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [
                {'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}
            ],
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        }

    def _call(self, name, args, call_id='c1'):
        return {
            'text': '',
            'tool_calls': [{'call_id': call_id, 'name': name, 'arguments': args}],
            'carry_inputs': [{
                'type': 'function_call', 'name': name,
                'arguments': json.dumps(args), 'call_id': call_id,
            }],
            'usage': {'input_tokens': 2, 'output_tokens': 1},
        }

    def _capture_calls(self):
        """Patch ``muk_mcp.tool._call`` and collect ``(name, arguments)``."""
        received = []

        def fake(self_arg, name, arguments, env, enforce_scope=None):
            received.append((name, arguments))
            return '{"ok": true}', {}

        return patch.object(
            type(self.env['muk_mcp.tool']), '_call', autospec=True, side_effect=fake,
        ), received

    def _texts(self, kind='text'):
        events = self.env['muk_ai.session.event'].sudo().search(
            [('session_id', '=', self.session.id), ('kind', '=', kind)], order='sequence',
        )
        return [e.payload.get('content') for e in events]

    # ------------------------------------------------------------------
    def test_text_event_revealed(self):
        with self._mock_responses([self._text(f'O CPF é {self.cpf_tok}.')]):
            self.session.start('qual o CPF?')
        self.assertIn(f'O CPF é {CPF}.', self._texts())
        self.assertNotIn(self.cpf_tok, json.dumps(self._texts()))

    def test_conversation_keeps_tokens(self):
        with self._mock_responses([self._text(f'O CPF é {self.cpf_tok}.')]):
            self.session.start('qual o CPF?')
        stored = json.dumps(self.session.conversation)
        self.assertIn(self.cpf_tok, stored)
        self.assertNotIn(CPF, stored.replace('qual o CPF?', ''))
        snapshot = self.session.get_snapshot(include_conversation=True)
        shown = json.dumps(snapshot['conversation'])
        self.assertIn(CPF, shown)
        self.assertNotIn(self.cpf_tok, shown)
        self.assertEqual(snapshot['last_text'], f'O CPF é {CPF}.')
        # the snapshot is a copy: the stored conversation still has the token
        self.assertIn(self.cpf_tok, json.dumps(self.session.conversation))

    def test_stream_split_token(self):
        published = []
        Session = type(self.session)

        def capture(session_self, event_type, payload):
            published.append((event_type, payload))

        state = {}
        head, rest = self.cpf_tok[:8], self.cpf_tok[8:]
        with patch.object(Session, '_publish_event', capture), \
                patch.object(Session, '_commit_safe', lambda s: None):
            self.session._coalesce_and_emit(
                state, 'text', 'last_text_flush', f'O CPF é {head}', 'text_delta',
            )
            self.session._coalesce_and_emit(
                state, 'text', 'last_text_flush', f'{rest}.', 'text_delta',
            )
            self.session._flush_stream_buffer(state)
        deltas = [p['delta'] for t, p in published if t == 'text_delta']
        self.assertEqual(''.join(deltas), f'O CPF é {CPF}.')
        self.assertFalse([d for d in deltas if '#' in d])

    def test_stream_split_keyword(self):
        """A token whose kind is cut in two is held back too."""
        published = []
        Session = type(self.session)

        def capture(session_self, event_type, payload):
            published.append((event_type, payload))

        state = {}
        head, rest = self.email_tok[:3], self.email_tok[3:]
        with patch.object(Session, '_publish_event', capture), \
                patch.object(Session, '_commit_safe', lambda s: None):
            for delta in (f'Escreva para {head}', rest, ' hoje.'):
                state['last_text_flush'] = 0.0  # force each delta out at once
                self.session._coalesce_and_emit(
                    state, 'text', 'last_text_flush', delta, 'text_delta',
                )
            self.session._flush_text_buffer(state)
        deltas = [p['delta'] for t, p in published if t == 'text_delta']
        self.assertEqual(''.join(deltas), f'Escreva para {EMAIL} hoje.')
        self.assertFalse([d for d in deltas if '#' in d])

    def test_tool_args_revealed(self):
        args = {
            'model': 'res.partner', 'domain': [['vat', '=', self.cpf_tok]],
            'fields': ['name'], 'limit': 1,
        }
        call_patch, received = self._capture_calls()
        with call_patch, self._mock_responses([
            self._call('search_read', args), self._text('ok'),
        ]):
            self.session.start('busque o cliente')
        [(name, sent)] = received
        self.assertEqual(name, 'search_read')
        self.assertEqual(sent['domain'], [['vat', '=', CPF]])
        # the tool-call event shows the real value, the conversation the token
        [event] = self.env['muk_ai.session.event'].sudo().search(
            [('session_id', '=', self.session.id), ('kind', '=', 'tool_call')],
        )
        self.assertIn(CPF, json.dumps(event.payload))
        self.assertIn(self.cpf_tok, json.dumps(self.session.conversation))

    def test_outbound_tool_args_keep_tokens(self):
        """Tools that send data to third parties keep the tokens (R26)."""
        call_patch, received = self._capture_calls()
        with call_patch:
            for name in ('generate_image', 'web_search', 'web_fetch'):
                self.session._dispatch_tool_call(
                    name, {'prompt': f'cartão com {self.cpf_tok}'}, f'c-{name}',
                )
            self.session._dispatch_tool_call(
                'search_read', {'model': 'res.partner', 'domain': [['vat', '=', self.cpf_tok]]},
                'c-odoo',
            )
        sent = dict(received)
        for name in ('generate_image', 'web_search', 'web_fetch'):
            self.assertEqual(sent[name]['prompt'], f'cartão com {self.cpf_tok}')
        self.assertEqual(sent['search_read']['domain'], [['vat', '=', CPF]])

    def test_approval_preview_detokenized(self):
        self._mark_sensitive('res.partner')
        partner = self.env['res.partner'].create({'name': 'Cliente Teste'})
        args = {'model': 'res.partner', 'ids': [partner.id], 'values': {'email': self.email_tok}}
        with self._mock_responses([self._call('update_records', args, 'u1')]):
            self.session.start('atualize o e-mail')
        self.assertEqual(self.session.state, 'waiting')
        pending = self.session.pending_ask
        self.assertEqual(pending['kind'], 'approval')
        self.assertIn(EMAIL, json.dumps(pending['preview']))
        public = json.dumps(self.session._public_pending_ask())
        self.assertNotIn('EMAIL#', public)
        self.assertNotIn('EMAIL#', json.dumps(self.session.get_snapshot()['pending_ask']))
        [ask] = self.env['muk_ai.session.event'].sudo().search(
            [('session_id', '=', self.session.id), ('kind', '=', 'ask_user')],
        )
        self.assertNotIn('EMAIL#', json.dumps(ask.payload))
        call_patch, received = self._capture_calls()
        with call_patch, self._mock_responses([self._text('feito')]):
            self.session.approve_tool()
        [(name, sent)] = received
        self.assertEqual(name, 'update_records')
        self.assertEqual(sent['values'], {'email': EMAIL})

    def test_ask_user_question_revealed(self):
        args = {'question': f'Confirmo o CPF {self.cpf_tok}?', 'resolution': 'yesno'}
        with self._mock_responses([self._call('ask_user', args, 'q1')]):
            self.session.start('confirme')
        self.assertEqual(self.session.state, 'waiting')
        public = self.session.get_snapshot()['pending_ask']
        self.assertEqual(public['text'], f'Confirmo o CPF {CPF}?')

    def test_disabled_still_reveals_old_tokens(self):
        """Switching tokens off later still shows the tokens already in the chat."""
        self.env['ir.config_parameter'].sudo().set_param('itbr_muk_ai_pii.enabled', 'False')
        with self._mock_responses([self._text(f'O CPF é {self.cpf_tok}.')]):
            self.session.start('qual o CPF?')
        self.assertIn(f'O CPF é {CPF}.', self._texts())
