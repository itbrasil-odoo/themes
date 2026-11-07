import json
import os
import re
from unittest.mock import patch

from odoo.tests import new_test_user
from odoo.tools import config

from odoo.addons.muk_ai.tests.common import AITestCommon

from ..tools.keys import make_token

KEY = 'test-key'
CPF = '12345678909'
EMAIL = 'joao@cliente.com.br'
NAME = 'Maria José Pessoa'


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
        self.name_tok = store._emit('NAME', NAME, self.session.sudo())
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

    def test_snapshot_flags_masking_for_the_composer(self):
        self.assertTrue(self.session.get_snapshot()['itbr_pii_enabled'])
        self.assertTrue(self.session.itbr_pii_enabled)
        self.env['ir.config_parameter'].sudo().set_param('itbr_muk_ai_pii.enabled', 'False')
        self.session.invalidate_recordset(['itbr_pii_enabled'])
        self.assertFalse(self.session.get_snapshot()['itbr_pii_enabled'])

    def test_stream_split_token(self):
        published = []
        Session = type(self.session)

        def capture(session_self, event_type, payload):
            published.append((event_type, payload))

        state = {}
        head, rest = self.cpf_tok[:8], self.cpf_tok[8:]
        with patch.object(Session, '_publish_event', capture), \
                patch.object(Session, '_commit_safe', lambda s: None):
            for delta in (f'O CPF é {head}', f'{rest}.'):
                state['last_text_flush'] = 0.0  # force each delta out at once
                self.session._coalesce_and_emit(
                    state, 'text', 'last_text_flush', delta, 'text_delta',
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
        # itbr_muk_ai_guard, when installed too, refuses the web tools
        self.env['ir.config_parameter'].sudo().set_param('itbr_muk_ai_guard.block_web', 'False')
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

    # -- fix round 1 ----------------------------------------------------
    def _stream(self, content_key, last_key, event_type, deltas, extra=None):
        """Feed ``deltas`` one by one, flushing each at once; return the published deltas."""
        published = []
        Session = type(self.session)

        def capture(session_self, kind, payload):
            published.append((kind, payload))

        state = {}
        with patch.object(Session, '_publish_event', capture), \
                patch.object(Session, '_commit_safe', lambda s: None):
            for delta in deltas:
                state[last_key] = 0.0
                self.session._coalesce_and_emit(
                    state, content_key, last_key, delta, event_type, extra=extra,
                )
            self.session._flush_stream_buffer(state)
        return [p for t, p in published if t == event_type]

    def test_stream_reasoning_revealed(self):
        head, rest = self.cpf_tok[:5], self.cpf_tok[5:]
        payloads = self._stream(
            'reasoning', 'last_reasoning_flush', 'reasoning_delta',
            [f'Busco o CPF {head}', f'{rest} no cadastro.'],
        )
        deltas = [p['delta'] for p in payloads]
        self.assertEqual(''.join(deltas), f'Busco o CPF {CPF} no cadastro.')
        self.assertFalse([d for d in deltas if '#' in d])

    def test_stream_tool_args_revealed(self):
        args = json.dumps({'domain': [['vat', '=', self.cpf_tok]]})
        cut = args.index('#') + 3
        payloads = self._stream(
            'tool_args_c1', 'tool_args_c1_last', 'tool_call_args_delta',
            [args[:cut], args[cut:]], extra={'call_id': 'c1'},
        )
        self.assertTrue(all(p.get('call_id') == 'c1' for p in payloads))
        deltas = [p['delta'] for p in payloads]
        self.assertEqual(''.join(deltas), args.replace(self.cpf_tok, CPF))
        self.assertFalse([d for d in deltas if '#' in d])

    def test_tool_output_echo_masked(self):
        """``open_view`` echoes its revealed domain: the provider gets the token back."""
        args = {
            'model': 'res.partner',
            'domain': json.dumps([['name', '=', self.name_tok]]),
            'name': f'Contatos de {self.name_tok}',
        }
        with self._mock_responses([self._call('open_view', args), self._text('ok')]) as mock:
            self.session.start('mostre')
        sent = json.dumps(mock.call_args_list[1].kwargs['inputs'], ensure_ascii=False)
        self.assertIn(self.name_tok, sent)
        self.assertNotIn('Maria', sent)
        pinned = json.dumps(self.session.view_context or {}, ensure_ascii=False)
        self.assertIn(self.name_tok, pinned)
        self.assertNotIn('Maria', pinned)
        self.assertNotIn('Maria', json.dumps(self.session.conversation, ensure_ascii=False))

    def test_tool_error_echo_masked(self):
        received = []

        def boom(self_arg, name, arguments, env, enforce_scope=None):
            received.append(arguments)
            raise ValueError(f"Invalid domain {arguments['domain']!r} for {NAME}")

        with patch.object(
            type(self.env['muk_mcp.tool']), '_call', autospec=True, side_effect=boom,
        ):
            output, ok = self.session._dispatch_tool_call(
                'search_read',
                {'model': 'res.partner', 'domain': [['name', '=', self.name_tok]]},
                'c-err',
            )
        self.assertFalse(ok)
        self.assertEqual(received[0]['domain'], [['name', '=', NAME]])
        self.assertIn(self.name_tok, output['error'])
        self.assertNotIn('Maria', output['error'])

    def test_unknown_tool_args_keep_tokens(self):
        call_patch, received = self._capture_calls()
        with call_patch:
            self.session._dispatch_tool_call(
                'remote_crm_lookup', {'query': f'cliente {self.cpf_tok}'}, 'c-remote',
            )
        [(name, sent)] = received
        self.assertEqual(sent['query'], f'cliente {self.cpf_tok}')

    def test_compaction_summary_shown_real_stored_token(self):
        summary = f'O cliente {self.name_tok} tem CPF {self.cpf_tok}.'
        shown = f'O cliente {NAME} tem CPF {CPF}.'
        sent = []

        def bus(session_self, channel, message, **kwargs):
            sent.append((channel, message))

        event = self.session._begin_compact_progress()
        with patch.object(type(self.session), '_bus_send', bus):
            self.session._patch_compact_progress(
                event, {'state': 'done', 'summary': summary, 'streamed_text': summary},
            )
        [update] = [m for c, m in sent if m.get('type') == 'compact_update']
        self.assertEqual(update['payload']['patch']['summary'], shown)
        self.assertEqual(update['payload']['patch']['streamed_text'], shown)
        # the stored summary keeps the tokens: it goes back to the provider
        self.assertEqual(event.payload['summary'], summary)
        self.assertEqual(self.session._find_prior_compact_summary(), summary)
        [window] = [
            e for e in self.session.fetch_events()['events'] if e['kind'] == 'compact_progress'
        ]
        self.assertEqual(window['summary'], shown)
        [snap] = [
            e for e in self.session.get_snapshot()['events'] if e['kind'] == 'compact_progress'
        ]
        self.assertEqual(snap['streamed_text'], shown)
        self.assertFalse(re.search(r'(CPF|NAME)#', json.dumps(snap)))

    # -- fix round 2 ----------------------------------------------------
    def _echo(self, arguments, output, name='search_read'):
        """Dispatch ``name`` with ``arguments``; the tool answers ``output``."""
        def fake(self_arg, tool, args, env, enforce_scope=None):
            return output, {}

        with patch.object(
            type(self.env['muk_mcp.tool']), '_call', autospec=True, side_effect=fake,
        ):
            result, ok = self.session._dispatch_tool_call(name, arguments, 'c-echo')
        self.assertTrue(ok)
        return result

    def test_view_context_revealed_for_the_user(self):
        args = {'model': 'res.partner', 'domain': json.dumps([['name', '=', self.name_tok]])}
        with self._mock_responses([self._call('open_view', args), self._text('ok')]):
            self.session.start('mostre')
        self.env.flush_all()
        self.env.cr.execute(
            'SELECT view_context::text FROM muk_ai_session WHERE id = %s', [self.session.id],
        )
        stored = self.env.cr.fetchone()[0]
        self.assertIn(self.name_tok, stored)
        self.assertNotIn('Maria', stored)
        shown = [
            self.session.get_snapshot()['view_context'],
            self.session._state_metrics()['view_context'],
            self.session.read(['view_context'])[0]['view_context'],
            self.session.web_read({'view_context': {}})[0]['view_context'],
        ]
        for value in shown:
            self.assertEqual(value['domain'], [['name', '=', NAME]])

    def test_view_context_kept_for_tools(self):
        """A chat tool reading the session gets the stored tokens, never the values."""
        self.session.view_context = {
            'kind': 'list', 'model': 'res.partner', 'domain': [['name', '=', self.name_tok]],
        }
        tool_env = self.session._tool_dispatch_env()
        [row] = tool_env['muk_ai.session'].browse(self.session.id).read(['view_context'])
        self.assertEqual(row['view_context']['domain'], [['name', '=', self.name_tok]])

    def test_echo_mask_structural(self):
        store = self.env['itbr.muk_ai.pii.token']
        doc_tok = store._emit('DOC', '4242', self.session.sudo())
        ana_tok = store._emit('NAME', 'Ana', self.session.sudo())
        rows = [{'id': 4242, 'ref': '4242', 'name': 'Ana', 'Ana': 1, 'note': 'Banana da Ana'}]
        output = self._echo(
            {'model': 'res.partner', 'domain': [['ref', '=', doc_tok], ['name', '=', ana_tok]]},
            json.dumps(rows, indent=2),
        )
        expected = [{
            'id': 4242, 'ref': doc_tok, 'name': ana_tok, 'Ana': 1, 'note': f'Banana da {ana_tok}',
        }]
        self.assertEqual(output, json.dumps(expected, indent=2))

    def test_echo_mask_case_insensitive(self):
        output = self._echo(
            {'model': 'res.partner', 'domain': [['name', '=', self.name_tok]]},
            'Contato MARIA JOSÉ PESSOA atualizado',
        )
        self.assertEqual(output, f'Contato {self.name_tok} atualizado')

    def test_echo_mask_formatted_cpf(self):
        output = self._echo(
            {'model': 'res.partner', 'domain': [['vat', '=', self.cpf_tok]]},
            json.dumps({'vat': '123.456.789-09', 'id': 7}),
        )
        self.assertEqual(json.loads(output), {'vat': self.cpf_tok, 'id': 7})

    def test_echo_mask_double_encoded(self):
        output = self._echo(
            {'model': 'res.partner', 'domain': [['name', '=', self.name_tok]]},
            json.dumps(json.dumps({'name': NAME})),
        )
        self.assertIn(self.name_tok, output)
        self.assertNotIn('Maria', output)
        self.assertNotIn('Pessoa', output)

    def test_stream_compaction_revealed(self):
        head, rest = self.name_tok[:6], self.name_tok[6:]
        payloads = self._stream(
            'buffer', 'buffer_last', 'compact_delta',
            [f'Cliente {head}', f'{rest} pediu.'], extra={'event_id': 1},
        )
        deltas = [p['delta'] for p in payloads]
        self.assertEqual(''.join(deltas), f'Cliente {NAME} pediu.')
        self.assertFalse([d for d in deltas if '#' in d])
