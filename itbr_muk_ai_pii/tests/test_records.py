import base64
import json
import os
from unittest.mock import patch

from odoo.tests import new_test_user
from odoo.tools import config

from odoo.addons.muk_ai.tests.common import AITestCommon

from ..tools.keys import make_token

KEY = 'test-key'
CPF = '12345678909'
CNPJ = '11222333000181'


def tok(kind, value):
    return make_token(kind, value, KEY)


class TestRecords(AITestCommon):
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
        self.env['ir.config_parameter'].sudo().set_param('itbr_muk_ai_pii.enabled', 'True')
        self.user = new_test_user(
            self.env, login='pii_rec_user', name='Vera Vendedora',
            groups='base.group_user,base.group_allow_export',
        )
        self.session = self.env['muk_ai.session'].with_user(self.user).create({'name': 'PII'})
        self.tool_env = self.session._tool_dispatch_env()
        Partner = self.env['res.partner']
        self.country = self.env.ref('base.br')
        self.person = Partner.create({
            'name': 'Maria Pessoa',
            'vat': '123.456.789-09',
            'email': 'Maria@Cliente.com.br',
            'phone': '(11) 98765-4321',
            'city': 'Campinas',
            'country_id': self.country.id,
        })
        self.company = Partner.create({
            'name': 'ACME Ltda',
            'is_company': True,
            'vat': '11.222.333/0001-81',
            'email': 'contato@acme.com.br',
        })
        self.child = Partner.create({'name': 'Filho Contato', 'parent_id': self.person.id})

    # ------------------------------------------------------------------
    def _call(self, name, arguments, env=None):
        env = env or self.tool_env
        text, _info = env['muk_mcp.tool']._call(name, arguments, env)
        return json.loads(text) if isinstance(text, str) else text

    def _read(self, records, fields, env=None):
        return self._call(
            'search_read',
            {'model': records._name, 'domain': [['id', 'in', records.ids]], 'fields': fields},
            env,
        )

    def _set_blocked(self, value):
        self.env['ir.config_parameter'].sudo().set_param('itbr_muk_ai_pii.blocked_models', value)

    # ------------------------------------------------------------------
    def test_dispatch_context_has_session(self):
        self.assertEqual(
            self.session._tool_dispatch_context().get('itbr_pii_session_id'), self.session.id
        )

    def test_person_partner_masked(self):
        [row] = self._read(self.person, ['name', 'display_name', 'vat', 'email', 'phone', 'city'])
        self.assertEqual(row['name'], tok('NAME', 'Maria Pessoa'))
        self.assertEqual(row['display_name'], tok('NAME', 'Maria Pessoa'))
        self.assertEqual(row['vat'], tok('CPF', CPF))
        self.assertEqual(row['email'], tok('EMAIL', 'maria@cliente.com.br'))
        self.assertEqual(row['phone'], tok('PHONE', '5511987654321'))
        self.assertEqual(row['city'], 'Campinas')

    def test_read_records_masked(self):
        [row] = self._call(
            'read_records', {'model': 'res.partner', 'ids': self.person.ids, 'fields': ['name', 'vat']}
        )
        self.assertEqual(row['name'], tok('NAME', 'Maria Pessoa'))
        self.assertEqual(row['vat'], tok('CPF', CPF))

    def test_token_revealed_for_session(self):
        [row] = self._read(self.person, ['vat'])
        store = self.env['itbr.muk_ai.pii.token']
        self.assertEqual(store._reveal(row['vat'], self.session), CPF)

    def test_company_partner(self):
        [row] = self._read(self.company, ['name', 'vat', 'email'])
        self.assertEqual(row['name'], 'ACME Ltda')
        self.assertEqual(row['vat'], tok('CNPJ', CNPJ))
        self.assertEqual(row['email'], tok('EMAIL', 'contato@acme.com.br'))

    def test_team_partner_readable(self):
        [row] = self._read(self.user.partner_id, ['name', 'display_name'])
        self.assertEqual(row['name'], 'Vera Vendedora')
        self.assertEqual(row['display_name'], 'Vera Vendedora')

    def test_team_employee_partner_readable(self):
        if 'hr.employee' not in self.env:
            self.skipTest('hr is not installed in the test database')
        contact = self.env['res.partner'].create({'name': 'Edu Funcionario'})
        self.env['hr.employee'].create({'name': 'Edu Funcionario', 'work_contact_id': contact.id})
        [row] = self._read(contact, ['name'])
        self.assertEqual(row['name'], 'Edu Funcionario')

    def test_many2one_person_name_tokenized(self):
        [row] = self._read(self.child, ['parent_id', 'name'])
        self.assertEqual(row['parent_id'], [self.person.id, tok('NAME', 'Maria Pessoa')])
        self.assertEqual(row['name'], tok('NAME', 'Filho Contato'))

    def test_many2one_company_and_team_readable(self):
        contact = self.env['res.partner'].create({'name': 'Joana', 'parent_id': self.company.id})
        [row] = self._read(contact, ['parent_id'])
        self.assertEqual(row['parent_id'], [self.company.id, 'ACME Ltda'])
        [row] = self._read(self.person, ['user_id', 'create_uid'])
        self.assertNotIn('#', json.dumps(row))

    def test_blocked_field_dropped(self):
        [row] = self._read(self.user, ['name', 'password'])
        self.assertNotIn('password', row)
        self.assertEqual(row['name'], 'Vera Vendedora')

    def test_blocked_comodel_many2one_false(self):
        self._set_blocked('res.partner.bank,res.country')
        [row] = self._read(self.person, ['country_id', 'city'])
        self.assertIs(row['country_id'], False)
        self.assertEqual(row['city'], 'Campinas')
        groups = self._call(
            'read_group',
            {'model': 'res.partner', 'domain': [['id', '=', self.person.id]], 'groupby': ['country_id']},
        )
        self.assertIs(groups[0]['country_id'], False)
        self.assertNotIn(str(self.country.id), json.dumps(groups[0].get('__extra_domain', [])))

    def test_external_mcp_drops_tokenized(self):
        [row] = self._read(self.person, ['name', 'vat', 'email', 'city'], env=self.env)
        self.assertNotIn('vat', row)
        self.assertNotIn('email', row)
        self.assertEqual(row['name'], 'Maria Pessoa')
        self.assertEqual(row['city'], 'Campinas')

    def test_external_cannot_claim_session(self):
        [row] = self._call(
            'search_read',
            {
                'model': 'res.partner',
                'domain': [['id', '=', self.person.id]],
                'fields': ['vat'],
                'context': {'itbr_pii_session_id': self.session.id},
            },
            env=self.env,
        )
        self.assertNotIn('vat', row)

    def test_tokens_disabled_values_real(self):
        del os.environ['ODOO_AI_PII_KEY']
        [row] = self._read(self.person, ['name', 'vat', 'email'])
        self.assertEqual(row['name'], 'Maria Pessoa')
        self.assertEqual(row['vat'], '123.456.789-09')
        self.assertEqual(row['email'], 'Maria@Cliente.com.br')

    def test_describe_hides_blocked(self):
        users = self._call('describe_model', {'model': 'res.users'})
        self.assertNotIn('password', users)
        self.assertIn('name', users)
        partner = self._call('describe_model', {'model': 'res.partner'})
        self.assertIn('vat', partner)
        external = self._call('describe_model', {'model': 'res.partner'}, env=self.env)
        self.assertNotIn('vat', external)
        self.assertIn('name', external)

    def test_read_group_partner_label_tokenized(self):
        groups = self._call(
            'read_group',
            {'model': 'res.partner', 'domain': [['id', '=', self.child.id]], 'groupby': ['parent_id']},
        )
        self.assertEqual(groups[0]['parent_id'], [self.person.id, tok('NAME', 'Maria Pessoa')])

    def test_read_group_tokenized_field(self):
        args = {
            'model': 'res.partner',
            'domain': [['id', '=', self.person.id]],
            'groupby': ['email'],
            'aggregates': ['vat:array_agg', 'vat:count_distinct'],
        }
        [group] = self._call('read_group', dict(args))
        self.assertEqual(group['email'], tok('EMAIL', 'maria@cliente.com.br'))
        self.assertEqual(group['vat:array_agg'], [tok('CPF', CPF)])
        self.assertEqual(group['vat:count_distinct'], 1)
        self.assertNotIn('Cliente', json.dumps(group))
        [group] = self._call('read_group', dict(args), env=self.env)
        self.assertIs(group['email'], False)
        self.assertNotIn('vat:array_agg', group)
        self.assertNotIn('Cliente', json.dumps(group))
        self.assertNotIn('123.456', json.dumps(group))

    def test_export_drops_tokenized(self):
        result = self._call(
            'export_records',
            {
                'model': 'res.partner',
                'ids': self.child.ids,
                'fields': ['city', 'vat', 'parent_id/email', 'parent_id/city'],
            },
        )
        content = base64.b64decode(result['content_base64']).decode('utf-8-sig')
        self.assertNotIn('vat', content)
        self.assertNotIn('email', content)
        self.assertIn('parent_id/city', content)
