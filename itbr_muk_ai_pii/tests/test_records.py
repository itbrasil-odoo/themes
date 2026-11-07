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
            groups='base.group_user,base.group_allow_export,base.group_partner_manager',
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

    def _export(self, fields, env=None):
        result = self._call(
            'export_records', {'model': 'res.partner', 'ids': self.child.ids, 'fields': fields}, env
        )
        return base64.b64decode(result['content_base64']).decode('utf-8-sig')

    def test_export_session_drops_blocked_only(self):
        self._set_blocked('res.partner.bank')
        content = self._export(['city', 'vat', 'parent_id/email', 'parent_id/city', 'user_ids/password'])
        self.assertIn('parent_id/email', content)
        self.assertIn('maria@cliente.com.br', content.lower())
        self.assertNotIn('password', content)

    def test_export_external_drops_tokenized(self):
        content = self._export(['city', 'vat', 'parent_id/email', 'parent_id/city'], env=self.env)
        self.assertNotIn('vat', content)
        self.assertNotIn('email', content)
        self.assertIn('parent_id/city', content)

    # -- fix round 1 -----------------------------------------------------
    def test_related_parent_name_tokenized(self):
        [row] = self._read(self.child, ['parent_name'])
        self.assertEqual(row['parent_name'], tok('NAME', 'Maria Pessoa'))
        contact = self.env['res.partner'].create({'name': 'Joana', 'parent_id': self.company.id})
        [row] = self._read(contact, ['parent_name'])
        self.assertEqual(row['parent_name'], 'ACME Ltda')

    def test_follower_name_tokenized(self):
        self.person.message_subscribe(partner_ids=self.person.ids)
        followers = self.env['mail.followers'].search(
            [('res_model', '=', 'res.partner'), ('res_id', '=', self.person.id),
             ('partner_id', '=', self.person.id)]
        )
        [row] = self._read(followers, ['name', 'partner_id'])
        self.assertEqual(row['name'], tok('NAME', 'Maria Pessoa'))

    def test_message_record_name_and_activity_res_name(self):
        message = self.person.message_post(body='hello', message_type='comment')
        [row] = self._read(message, ['record_name'])
        self.assertEqual(row['record_name'], tok('NAME', 'Maria Pessoa'))
        activity = self.env['mail.activity'].create({
            'res_model_id': self.env.ref('base.model_res_partner').id,
            'res_id': self.person.id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
            'user_id': self.user.id,
        })
        [row] = self._read(activity.sudo(), ['res_name'], env=self.tool_env(su=True))
        self.assertEqual(row['res_name'], tok('NAME', 'Maria Pessoa'))
        company_message = self.company.message_post(body='hi', message_type='comment')
        [row] = self._read(company_message, ['record_name'])
        self.assertEqual(row['record_name'], 'ACME Ltda')

    def test_portal_user_name_tokenized(self):
        portal = new_test_user(
            self.env, login='Portal@Cliente.com.br', name='Paula Portal', groups='base.group_portal'
        )
        [row] = self._read(portal, ['name', 'display_name', 'login'], env=self.tool_env(su=True))
        self.assertEqual(row['name'], tok('NAME', 'Paula Portal'))
        self.assertEqual(row['display_name'], tok('NAME', 'Paula Portal'))
        self.assertEqual(row['login'], tok('EMAIL', 'portal@cliente.com.br'))
        [row] = self._read(self.user, ['name'])
        self.assertEqual(row['name'], 'Vera Vendedora')

    def test_contact_address_tokenized(self):
        self.person.write({'street': 'Rua das Flores 10', 'zip': '13000-000'})
        [row] = self._read(self.person, ['contact_address'])
        self.assertTrue(row['contact_address'].startswith('ADDR#'))
        [row] = self._read(self.person, ['contact_address', 'name'], env=self.env)
        self.assertNotIn('contact_address', row)

    def test_kinds_login_place_of_birth(self):
        from ..tools.records import field_kind
        self.assertEqual(field_kind('login', 'a@b.com'), 'EMAIL')
        self.assertEqual(field_kind('place_of_birth', 'Campinas'), 'ADDR')
        self.assertEqual(field_kind('email_address', 'a@b.com'), 'EMAIL')
        self.assertEqual(field_kind('contact_address', 'Rua X'), 'ADDR')
        self.assertEqual(field_kind('birthday', '2000-01-01'), 'DATE')

    def test_get_messages_author_tokenized(self):
        self.person.with_context(mail_create_nolog=True).message_post(
            body='hello', message_type='comment', author_id=self.person.id
        )
        messages = self._call('get_messages', {'model': 'res.partner', 'id': self.person.id})
        authors = [m['author_id'] for m in messages if m['author_id']]
        self.assertIn([self.person.id, tok('NAME', 'Maria Pessoa')], authors)
        self.assertNotIn('Maria Pessoa', json.dumps(messages))

    def test_tracking_value_partner_name_tokenized(self):
        message = self.child.message_post(body='', message_type='notification')
        Tracking = self.env['mail.tracking.value'].sudo()
        parent_field = self.env['ir.model.fields']._get('res.partner', 'parent_id')
        email_field = self.env['ir.model.fields']._get('res.partner', 'email')
        values = Tracking.create([
            {'mail_message_id': message.id, 'field_id': parent_field.id,
             'old_value_integer': self.company.id, 'old_value_char': 'ACME Ltda',
             'new_value_integer': self.person.id, 'new_value_char': 'Maria Pessoa'},
            {'mail_message_id': message.id, 'field_id': email_field.id,
             'old_value_char': 'old@cliente.com.br', 'new_value_char': 'Maria@Cliente.com.br'},
        ])
        fields = ['old_value_char', 'new_value_char']
        rows = sorted(self._read(values, fields, env=self.tool_env(su=True)), key=lambda r: r['id'])
        self.assertEqual(rows[0]['old_value_char'], 'ACME Ltda')
        self.assertEqual(rows[0]['new_value_char'], tok('NAME', 'Maria Pessoa'))
        self.assertEqual(rows[1]['new_value_char'], tok('EMAIL', 'maria@cliente.com.br'))
        external = self._read(values, fields, env=self.env)
        self.assertNotIn('cliente.com.br', json.dumps(external))

    def test_call_method_read_tokenized(self):
        rows = self._call(
            'call_method',
            {'model': 'res.partner', 'method': 'read', 'ids': self.person.ids,
             'kwargs': {'fields': ['name', 'vat', 'email']}},
        )
        self.assertEqual(rows[0]['name'], tok('NAME', 'Maria Pessoa'))
        self.assertEqual(rows[0]['vat'], tok('CPF', CPF))

    def test_call_method_search_read_and_name_search(self):
        rows = self._call(
            'call_method',
            {'model': 'res.partner', 'method': 'search_read',
             'kwargs': {'domain': [['id', '=', self.child.id]], 'fields': ['parent_id', 'email']}},
        )
        self.assertEqual(rows[0]['parent_id'], [self.person.id, tok('NAME', 'Maria Pessoa')])
        pairs = self._call(
            'call_method',
            {'model': 'res.partner', 'method': 'name_search', 'kwargs': {'name': 'Maria Pessoa'}},
        )
        self.assertIn([self.person.id, tok('NAME', 'Maria Pessoa')], pairs)
        self.assertNotIn('Maria Pessoa', json.dumps(pairs))

    def test_call_method_web_read_and_read_group(self):
        rows = self._call(
            'call_method',
            {'model': 'res.partner', 'method': 'web_read', 'ids': self.child.ids,
             'kwargs': {'specification': {'name': {}, 'parent_id': {'fields': {'display_name': {}}}}}},
        )
        self.assertEqual(rows[0]['parent_id'], {'id': self.person.id, 'display_name': tok('NAME', 'Maria Pessoa')})
        groups = self._call(
            'call_method',
            {'model': 'res.partner', 'method': 'read_group',
             'kwargs': {'domain': [['id', '=', self.child.id]], 'fields': ['parent_id'],
                        'groupby': ['parent_id']}},
        )
        self.assertEqual(groups[0]['parent_id'][1], tok('NAME', 'Maria Pessoa'))
        self.assertNotIn('Maria Pessoa', json.dumps(groups))

    def test_many2one_portal_user_tokenized(self):
        portal = new_test_user(
            self.env, login='portal2@cliente.com.br', name='Paulo Portal', groups='base.group_portal'
        )
        self.person.user_id = portal
        self.company.user_id = self.user
        rows = sorted(self._read(self.person | self.company, ['user_id']), key=lambda r: r['id'])
        self.assertEqual(rows[0]['user_id'], [portal.id, tok('NAME', 'Paulo Portal')])
        self.assertEqual(rows[1]['user_id'], [self.user.id, 'Vera Vendedora'])
        groups = self._call(
            'read_group',
            {'model': 'res.partner', 'domain': [['id', '=', self.person.id]], 'groupby': ['user_id']},
        )
        self.assertEqual(groups[0]['user_id'], [portal.id, tok('NAME', 'Paulo Portal')])

    # -- fix round 2 -----------------------------------------------------
    def _legacy_group(self, env=None):
        return self._call(
            'call_method',
            {'model': 'res.partner', 'method': 'read_group',
             'kwargs': {'domain': [['id', '=', self.person.id]],
                        'fields': ['cpfs:array_agg(vat)', 'n:array_agg(name)'],
                        'groupby': ['is_company']}},
            env,
        )

    def test_read_group_alias_session(self):
        [group] = self._legacy_group()
        self.assertEqual(group['cpfs'], [tok('CPF', CPF)])
        self.assertEqual(group['n'], [tok('NAME', 'Maria Pessoa')])
        self.assertNotIn('123.456', json.dumps(group))

    def test_read_group_alias_external(self):
        [group] = self._legacy_group(env=self.env)
        self.assertNotIn('cpfs', group)
        self.assertNotIn('123.456', json.dumps(group))

    def test_read_group_unknown_key_dropped(self):
        from ..tools.records import Masker
        masker = Masker(self.tool_env, self.session.sudo())
        [group] = masker.groups('res.partner', [], [], [{'weird': 'Maria Pessoa', '__count': 1}])
        self.assertNotIn('weird', group)
        self.assertEqual(group['__count'], 1)

    def test_follower_display_name_tokenized(self):
        self.person.message_subscribe(partner_ids=self.person.ids)
        followers = self.env['mail.followers'].search(
            [('res_model', '=', 'res.partner'), ('res_id', '=', self.person.id),
             ('partner_id', '=', self.person.id)]
        )
        [row] = self._read(followers, ['display_name'])
        self.assertEqual(row['display_name'], tok('NAME', 'Maria Pessoa'))

    def test_call_method_web_read_group(self):
        result = self._call(
            'call_method',
            {'model': 'res.partner', 'method': 'web_read_group',
             'kwargs': {'domain': [['id', '=', self.child.id]], 'groupby': ['parent_id'],
                        'auto_unfold': True,
                        'unfold_read_specification': {'name': {}, 'parent_name': {}}}},
        )
        self.assertEqual(result['groups'][0]['parent_id'], [self.person.id, tok('NAME', 'Maria Pessoa')])
        self.assertNotIn('Maria Pessoa', json.dumps(result))
        self.assertNotIn('Filho Contato', json.dumps(result))

    def test_call_method_web_save(self):
        rows = self._call(
            'call_method',
            {'model': 'res.partner', 'method': 'web_save', 'ids': self.person.ids,
             'kwargs': {'vals': {'city': 'Sorocaba'},
                        'specification': {'name': {}, 'vat': {}, 'city': {}}}},
        )
        self.assertEqual(rows[0]['name'], tok('NAME', 'Maria Pessoa'))
        self.assertEqual(rows[0]['vat'], tok('CPF', CPF))
        self.assertEqual(rows[0]['city'], 'Sorocaba')

    # -- fix round 3 -----------------------------------------------------
    def _group_call(self, method, kwargs):
        return self._call('call_method', {'model': 'res.partner', 'method': method, 'kwargs': kwargs})

    def test_read_group_alias_colliding_with_groupby_refused(self):
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self._group_call('read_group', {
                'domain': [['id', '=', self.person.id]],
                'fields': ['is_company:array_agg(vat)'], 'groupby': ['is_company'],
            })

    def test_read_group_alias_meta_key_refused(self):
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self._group_call('read_group', {
                'domain': [['id', '=', self.person.id]],
                'fields': ['__count:array_agg(vat)'], 'groupby': ['is_company', 'city'],
                'lazy': False,
            })
        with self.assertRaises(UserError):
            self._group_call('formatted_read_group', {
                'domain': [['id', '=', self.person.id]],
                'groupby': ['is_company'], 'aggregates': ['__fold:array_agg'],
            })

    def test_read_group_count_survives(self):
        [group] = self._group_call('read_group', {
            'domain': [['id', '=', self.person.id]], 'fields': ['city'],
            'groupby': ['is_company', 'city'], 'lazy': False,
        })
        self.assertEqual(group['__count'], 1)
        from ..tools.records import Masker
        masker = Masker(self.tool_env, self.session.sudo())
        [group] = masker.groups('res.partner', [], [], [{'__count': ['x'], '__fold': 'y'}])
        self.assertNotIn('__count', group)
        self.assertNotIn('__fold', group)
