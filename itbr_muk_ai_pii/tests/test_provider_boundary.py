import copy
import json
import os
from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests import new_test_user
from odoo.tools import config

from odoo.addons.muk_ai.tests.common import AITestCommon

from ..tools.keys import make_token

KEY = 'test-key'
CPF = '12345678909'
CPF_TEXT = '123.456.789-09'


def tok(kind, value):
    return make_token(kind, value, KEY)


def texts(inputs):
    """Every text the provider reads in ``inputs``, as one string."""
    return json.dumps(inputs, ensure_ascii=False, default=str)


class TestProviderBoundary(AITestCommon):
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
        self.params = self.env['ir.config_parameter'].sudo()
        self.params.set_param('itbr_muk_ai_pii.enabled', 'True')
        self.params.set_param('itbr_muk_ai_pii.email_domains', '')
        self.user = new_test_user(
            self.env, login='pii_bnd_user', name='Vera Vendedora',
            groups='base.group_user,base.group_partner_manager',
        )
        self.session = self.env['muk_ai.session'].with_user(self.user).create({'name': 'PII'})

    # ------------------------------------------------------------------
    @contextmanager
    def _capture(self, payloads):
        """Mock the provider and collect the ``inputs`` of every request."""
        captured = []
        with self._mock_responses(payloads) as mock:
            yield captured
            captured.extend(copy.deepcopy(c.kwargs['inputs']) for c in mock.call_args_list)

    def _text(self, text='done'):
        return {
            'text': text,
            'tool_calls': [],
            'carry_inputs': [
                {'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}
            ],
            'usage': {'input_tokens': 1, 'output_tokens': 1},
        }

    def _call_payload(self, call_id='c1'):
        args = {'model': 'res.partner', 'domain': [], 'fields': ['name'], 'limit': 1}
        return {
            'text': '',
            'tool_calls': [{'call_id': call_id, 'name': 'search_read', 'arguments': args}],
            'carry_inputs': [{
                'type': 'function_call', 'name': 'search_read',
                'arguments': json.dumps(args), 'call_id': call_id,
            }],
            'usage': {'input_tokens': 2, 'output_tokens': 1},
        }

    def _ui_ctx(self, inputs):
        found = [
            block['text']
            for item in inputs if isinstance(item, dict)
            for block in item.get('content') or [] if isinstance(block, dict)
            and str(block.get('text', '')).startswith('<ui_ctx>')
        ]
        self.assertTrue(found, 'no ui_ctx message sent')
        return found[-1]

    # ------------------------------------------------------------------
    def test_user_message_cpf_tokenized(self):
        with self._capture([self._text()]) as captured:
            self.session.start(f'O CPF do cliente é {CPF_TEXT}')
        sent = texts(captured[0])
        self.assertIn(tok('CPF', CPF), sent)
        self.assertNotIn(CPF_TEXT, sent)
        self.assertIn(CPF_TEXT, texts(self.session.conversation))

    def test_assistant_text_tokenized(self):
        self.session.conversation = [
            {'role': 'user', 'content': [{'type': 'input_text', 'text': 'oi'}]},
            {'type': 'message', 'content': [{'type': 'output_text', 'text': f'CPF {CPF_TEXT}'}]},
        ]
        inputs = self.session._build_request_inputs()
        self.assertIn(tok('CPF', CPF), texts(inputs))
        self.assertNotIn(CPF_TEXT, texts(inputs))
        self.assertIn(CPF_TEXT, texts(self.session.conversation))

    def test_tool_output_note_tokenized(self):
        note = json.dumps({'note': 'escreva para joao@cliente.com.br'})
        tool_patch, calls = self._patch_tool({'search_read': note})
        with tool_patch, self._capture([self._call_payload(), self._text()]) as captured:
            self.session.start('busque')
        self.assertIn('search_read', calls)
        outputs = [
            item for item in captured[1]
            if isinstance(item, dict) and item.get('type') == 'function_call_output'
        ]
        self.assertTrue(outputs)
        sent = texts(captured[1])
        self.assertIn(tok('EMAIL', 'joao@cliente.com.br'), sent)
        self.assertNotIn('joao@cliente.com.br', sent)
        # function_call arguments are written by the model and stay as they are
        self.assertTrue(any(i.get('type') == 'function_call' for i in captured[1] if isinstance(i, dict)))

    def test_allowed_email_domain_kept(self):
        self.params.set_param('itbr_muk_ai_pii.email_domains', 'dedicata.com.br, other.org')
        with self._capture([self._text()]) as captured:
            self.session.start('fale com renan@dedicata.com.br e ana@cliente.com.br')
        sent = texts(captured[0])
        self.assertIn('renan@dedicata.com.br', sent)
        self.assertIn(tok('EMAIL', 'ana@cliente.com.br'), sent)

    def test_system_message_tokenized(self):
        self.session.agent_id = self.env['muk_ai.agent'].create({
            'name': 'PII agent', 'system_prompt': f'Contato do cliente: {CPF_TEXT}',
        })
        system = self.session._build_request_inputs()[0]
        self.assertEqual(system['role'], 'system')
        self.assertIn(tok('CPF', CPF), texts(system))
        self.assertNotIn(CPF_TEXT, texts(system))

    def test_compaction_tokenized(self):
        prefix = [{'role': 'user', 'content': [{'type': 'input_text', 'text': f'CPF {CPF_TEXT}'}]}]
        original = copy.deepcopy(prefix)
        inputs = self.session._build_compact_inputs(prefix)
        self.assertIn(tok('CPF', CPF), texts(inputs))
        self.assertNotIn(CPF_TEXT, texts(inputs))
        self.assertEqual(prefix, original)

    def test_disabled_passes_unchanged(self):
        self.params.set_param('itbr_muk_ai_pii.enabled', 'False')
        with self._capture([self._text()]) as captured:
            self.session.start(f'CPF {CPF_TEXT}')
        sent = texts(captured[0])
        self.assertIn(CPF_TEXT, sent)
        self.assertNotIn('CPF#', sent)

    def test_round_count_unchanged(self):
        tool_patch, _calls = self._patch_tool({'search_read': '[]'})
        with tool_patch, self._mock_responses([self._call_payload(), self._text()]) as mock:
            self.session.start(f'busque {CPF_TEXT}')
        self.assertEqual(mock.call_count, 2)

    # -- R19: the open record of the screen ------------------------------
    def test_ui_ctx_person_partner_name_tokenized(self):
        person = self.env['res.partner'].create({'name': 'Maria Pessoa'})
        self.session.view_context = {
            'kind': 'record', 'model': 'res.partner', 'id': person.id,
            'display_name': 'Maria Pessoa',
        }
        with self._capture([self._text()]) as captured:
            self.session.start('resuma este contato')
        ctx = self._ui_ctx(captured[0])
        self.assertIn(tok('NAME', 'Maria Pessoa'), ctx)
        self.assertNotIn('Maria Pessoa', texts(captured[0]))
        # the user's screen keeps the real name
        self.assertEqual(self.session.view_context['display_name'], 'Maria Pessoa')

    def test_ui_ctx_company_and_team_readable(self):
        company = self.env['res.partner'].create({'name': 'ACME Ltda', 'is_company': True})
        self.session.view_context = {
            'kind': 'record', 'model': 'res.partner', 'id': company.id, 'display_name': 'ACME Ltda',
        }
        self.assertIn('"ACME Ltda"', self._ui_ctx(self.session._build_request_inputs()))
        team = self.user.partner_id
        self.session.view_context = {
            'kind': 'record', 'model': 'res.partner', 'id': team.id, 'display_name': team.name,
        }
        self.assertIn('"Vera Vendedora"', self._ui_ctx(self.session._build_request_inputs()))

    def test_ui_ctx_portal_user_name_tokenized(self):
        portal = new_test_user(
            self.env, login='pii_bnd_portal', name='Paulo Portal', groups='base.group_portal',
        )
        self.session.view_context = {
            'kind': 'record', 'model': 'res.users', 'id': portal.id, 'display_name': 'Paulo Portal',
        }
        ctx = self._ui_ctx(self.session._build_request_inputs())
        self.assertIn(tok('NAME', 'Paulo Portal'), ctx)
        self.assertNotIn('Paulo Portal', ctx)
        self.session.view_context = {
            'kind': 'record', 'model': 'res.users', 'id': self.user.id,
            'display_name': 'Vera Vendedora',
        }
        self.assertIn('"Vera Vendedora"', self._ui_ctx(self.session._build_request_inputs()))
