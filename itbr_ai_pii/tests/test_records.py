import json
import os
from unittest.mock import patch

from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase
from odoo.tools import config

from ..tools.keys import make_token

KEY = 'test-key'
CPF = '12345678909'
CNPJ = '11222333000181'


def tok(kind, value):
    return make_token(kind, value, KEY)


@tagged('post_install', '-at_install')
class TestRecords(TransactionCase):
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
        self.env['ir.config_parameter'].sudo().set_bool('itbr_ai_pii.enabled', True)
        self.user = new_test_user(
            self.env, login='pii_rec_user', name='Vera Vendedora',
            groups='base.group_user,base.group_partner_manager',
        )
        self.uenv = self.env(user=self.user)
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
        self.Token = self.env['itbr.ai.pii.token']

    # ------------------------------------------------------------------
    def _masker(self, external=False, env=None):
        return (env or self.uenv)['itbr.ai.pii']._masker(external=external)

    def _read(self, records, fields, external=False, env=None):
        env = env or self.uenv
        rows = env[records._name].search_read([('id', 'in', records.ids)], fields)
        return self._masker(external, env).rows(records._name, rows)

    def _group(self, model, domain, groupby, aggregates=(), external=False):
        groups = self.uenv[model].formatted_read_group(domain, groupby, list(aggregates))
        return self._masker(external).groups(model, groupby, list(aggregates), groups)

    def _set_blocked(self, value):
        self.env['ir.config_parameter'].sudo().set_str('itbr_ai_pii.blocked_models', value)

    def _require(self, model):
        if model not in self.env:
            self.skipTest(f'{model} is not installed in the test database')

    # -- brief ----------------------------------------------------------
    def test_person_partner_masked_company_readable(self):
        rows = sorted(
            self._read(self.person | self.company, ['name', 'vat', 'email', 'phone']),
            key=lambda r: r['id'],
        )
        person, company = rows
        self.assertEqual(person['name'], tok('NAME', 'Maria Pessoa'))
        self.assertEqual(person['vat'], tok('CPF', CPF))
        self.assertEqual(person['email'], tok('EMAIL', 'maria@cliente.com.br'))
        self.assertEqual(person['phone'], tok('PHONE', '5511987654321'))
        self.assertEqual(company['name'], 'ACME Ltda')
        self.assertEqual(company['vat'], tok('CNPJ', CNPJ))

    def test_team_names_readable(self):
        [row] = self._read(self.user.partner_id, ['name', 'display_name'])
        self.assertEqual(row['name'], 'Vera Vendedora')
        self.assertEqual(row['display_name'], 'Vera Vendedora')

    def test_external_masker_blocks_tokenized_fields(self):
        before = self.Token.sudo().search_count([])
        [row] = self._read(self.person, ['name', 'vat', 'email', 'city'], external=True)
        self.assertNotIn('vat', row)
        self.assertNotIn('email', row)
        self.assertEqual(row['name'], 'Maria Pessoa')
        self.assertEqual(row['city'], 'Campinas')
        self.assertEqual(self.Token.sudo().search_count([]), before)
        masker = self._masker(external=True)
        self.assertFalse(masker.visible('res.partner', 'vat'))
        self.assertTrue(masker.visible('res.partner', 'city'))

    def test_mask_text_detects_and_remasks_known(self):
        pii = self.uenv['itbr.ai.pii']
        token = self.uenv['itbr.ai.pii.token']._emit('NAME', 'João Silva')
        text = pii._mask_text('Fale com João Silva, CPF 529.982.247-25')
        self.assertNotIn('João Silva', text)
        self.assertNotIn('529.982.247-25', text)
        self.assertIn(token, text)
        self.assertIn(tok('CPF', '52998224725'), text)

    def test_remask_whole_words_only(self):
        pii = self.uenv['itbr.ai.pii']
        self.uenv['itbr.ai.pii.token']._emit('NAME', 'Ana')
        self.assertEqual(pii._mask_text('Banana e Mariana'), 'Banana e Mariana')
        self.assertNotIn('Ana', pii._mask_text('Fale com Ana.'))

    def test_remask_revealed_bare_values(self):
        pii = self.uenv['itbr.ai.pii']
        store = self.uenv['itbr.ai.pii.token']
        phone = store._emit('PHONE', '5511987654321')
        email = store._emit('EMAIL', 'joao@cliente.com.br')
        cpf = store._emit('CPF', '52998224725')
        self.assertEqual(pii._mask_text('Ligue 5511987654321.'), f'Ligue {phone}.')
        self.assertEqual(
            pii._mask_text("[('phone','=','5511987654321')]"), f"[('phone','=','{phone}')]"
        )
        self.assertEqual(pii._mask_text('Mande a JOAO@cliente.com.br.'), f'Mande a {email}.')
        self.assertEqual(pii._mask_text('CPF 52998224725'), f'CPF {cpf}')
        # whole numbers and addresses only
        self.assertEqual(pii._mask_text('9955119876543210'), '9955119876543210')
        self.assertNotIn(email, pii._mask_text('x.joao@cliente.com.br'))

    def test_mask_text_is_stable(self):
        pii = self.uenv['itbr.ai.pii']
        self.uenv['itbr.ai.pii.token']._emit('NAME', 'João Silva')
        self.uenv['itbr.ai.pii.token']._emit('NAME', 'João')
        text = 'João Silva e João, CPF 529.982.247-25, joao@cliente.com.br, (11) 98765-4321'
        first = pii._mask_text(text)
        self.assertEqual(first.encode(), pii._mask_text(text).encode())
        self.assertNotIn('João', first)

    def test_mask_text_without_tokens_unchanged(self):
        del os.environ['ODOO_AI_PII_KEY']
        text = 'CPF 529.982.247-25'
        self.assertEqual(self.uenv['itbr.ai.pii']._mask_text(text), text)

    def test_mask_any_walks_dicts_and_lists(self):
        data = {'a': ['CPF 529.982.247-25', {'b': 'x'}], 'n': 3}
        masked = self.uenv['itbr.ai.pii']._mask_any(data)
        self.assertEqual(masked['a'][0], f"CPF {tok('CPF', '52998224725')}")
        self.assertEqual(masked['a'][1], {'b': 'x'})
        self.assertEqual(masked['n'], 3)

    # -- ported ---------------------------------------------------------
    def test_person_partner_masked(self):
        [row] = self._read(self.person, ['name', 'display_name', 'vat', 'email', 'phone', 'city'])
        self.assertEqual(row['name'], tok('NAME', 'Maria Pessoa'))
        self.assertEqual(row['display_name'], tok('NAME', 'Maria Pessoa'))
        self.assertEqual(row['vat'], tok('CPF', CPF))
        self.assertEqual(row['email'], tok('EMAIL', 'maria@cliente.com.br'))
        self.assertEqual(row['phone'], tok('PHONE', '5511987654321'))
        self.assertEqual(row['city'], 'Campinas')

    def test_token_revealed_for_user(self):
        [row] = self._read(self.person, ['vat'])
        self.assertEqual(self.uenv['itbr.ai.pii.token']._reveal(row['vat']), CPF)
        other = new_test_user(self.env, login='pii_rec_other', groups='base.group_user')
        self.assertEqual(self.env(user=other)['itbr.ai.pii.token']._reveal(row['vat']), row['vat'])

    def test_company_partner(self):
        [row] = self._read(self.company, ['name', 'vat', 'email'])
        self.assertEqual(row['name'], 'ACME Ltda')
        self.assertEqual(row['vat'], tok('CNPJ', CNPJ))
        self.assertEqual(row['email'], tok('EMAIL', 'contato@acme.com.br'))

    def test_team_employee_partner_readable(self):
        self._require('hr.employee')
        contact = self.env['res.partner'].create({'name': 'Edu Funcionario'})
        self.env['hr.employee'].create({'name': 'Edu Funcionario', 'work_contact_id': contact.id})
        [row] = self._read(contact, ['name'])
        self.assertEqual(row['name'], 'Edu Funcionario')

    def test_many2one_person_name_tokenized(self):
        [row] = self._read(self.child, ['parent_id', 'name'])
        self.assertEqual(list(row['parent_id']), [self.person.id, tok('NAME', 'Maria Pessoa')])
        self.assertEqual(row['name'], tok('NAME', 'Filho Contato'))

    def test_many2one_company_and_team_readable(self):
        contact = self.env['res.partner'].create({'name': 'Joana', 'parent_id': self.company.id})
        [row] = self._read(contact, ['parent_id'])
        self.assertEqual(list(row['parent_id']), [self.company.id, 'ACME Ltda'])
        [row] = self._read(self.person, ['user_id', 'create_uid'])
        self.assertNotIn('#', json.dumps(row))

    def test_blocked_field_dropped(self):
        rows = self._masker().rows(
            'res.users', [{'id': self.user.id, 'name': 'Vera Vendedora', 'password': 'secret'}]
        )
        self.assertNotIn('password', rows[0])
        self.assertEqual(rows[0]['name'], 'Vera Vendedora')

    def test_blocked_comodel_many2one_false(self):
        self._set_blocked('res.partner.bank,res.country')
        [row] = self._read(self.person, ['country_id', 'city'])
        self.assertIs(row['country_id'], False)
        self.assertEqual(row['city'], 'Campinas')
        groups = self._group('res.partner', [('id', '=', self.person.id)], ['country_id'])
        self.assertIs(groups[0]['country_id'], False)
        self.assertNotIn(str(self.country.id), json.dumps(groups[0].get('__extra_domain', [])))

    def test_tokens_disabled_values_real(self):
        del os.environ['ODOO_AI_PII_KEY']
        [row] = self._read(self.person, ['name', 'vat', 'email'])
        self.assertEqual(row['name'], 'Maria Pessoa')
        self.assertEqual(row['vat'], self.person.vat)
        self.assertEqual(row['email'], 'Maria@Cliente.com.br')

    def test_read_group_partner_label_tokenized(self):
        groups = self._group('res.partner', [('id', '=', self.child.id)], ['parent_id'])
        self.assertEqual(list(groups[0]['parent_id']), [self.person.id, tok('NAME', 'Maria Pessoa')])

    def test_read_group_tokenized_field(self):
        args = ('res.partner', [('id', '=', self.person.id)], ['email'],
                ['vat:array_agg', 'vat:count_distinct'])
        [group] = self._group(*args)
        self.assertEqual(group['email'], tok('EMAIL', 'maria@cliente.com.br'))
        self.assertEqual(group['vat:array_agg'], [tok('CPF', CPF)])
        self.assertEqual(group['vat:count_distinct'], 1)
        self.assertNotIn('Cliente', json.dumps(group, default=str))
        [group] = self._group(*args, external=True)
        self.assertIs(group['email'], False)
        self.assertNotIn('vat:array_agg', group)
        self.assertNotIn('Cliente', json.dumps(group, default=str))
        self.assertNotIn('123.456', json.dumps(group, default=str))

    def test_related_parent_name_tokenized(self):
        [row] = self._read(self.child, ['parent_name'])
        self.assertEqual(row['parent_name'], tok('NAME', 'Maria Pessoa'))
        contact = self.env['res.partner'].create({'name': 'Joana', 'parent_id': self.company.id})
        [row] = self._read(contact, ['parent_name'])
        self.assertEqual(row['parent_name'], 'ACME Ltda')

    def _person_followers(self):
        self._require('mail.followers')
        self.person.message_subscribe(partner_ids=self.person.ids)
        return self.env['mail.followers'].search(
            [('res_model', '=', 'res.partner'), ('res_id', '=', self.person.id),
             ('partner_id', '=', self.person.id)]
        )

    def test_follower_name_tokenized(self):
        followers = self._person_followers()
        [row] = self._read(followers, ['name', 'partner_id'], env=self.env)
        self.assertEqual(row['name'], tok('NAME', 'Maria Pessoa'))

    def test_follower_display_name_tokenized(self):
        followers = self._person_followers()
        [row] = self._read(followers, ['display_name'], env=self.env)
        self.assertEqual(row['display_name'], tok('NAME', 'Maria Pessoa'))

    def test_message_record_name_and_activity_res_name(self):
        self._require('mail.activity')
        message = self.person.message_post(body='hello', message_type='comment')
        [row] = self._read(message, ['record_name'], env=self.env)
        self.assertEqual(row['record_name'], tok('NAME', 'Maria Pessoa'))
        activity = self.env['mail.activity'].create({
            'res_model_id': self.env.ref('base.model_res_partner').id,
            'res_id': self.person.id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
            'user_id': self.user.id,
        })
        [row] = self._read(activity, ['res_name'], env=self.env)
        self.assertEqual(row['res_name'], tok('NAME', 'Maria Pessoa'))
        company_message = self.company.message_post(body='hi', message_type='comment')
        [row] = self._read(company_message, ['record_name'], env=self.env)
        self.assertEqual(row['record_name'], 'ACME Ltda')

    def test_portal_user_name_tokenized(self):
        portal = new_test_user(
            self.env, login='Portal@Cliente.com.br', name='Paula Portal', groups='base.group_portal'
        )
        [row] = self._read(portal, ['name', 'display_name', 'login'], env=self.env)
        self.assertEqual(row['name'], tok('NAME', 'Paula Portal'))
        self.assertEqual(row['display_name'], tok('NAME', 'Paula Portal'))
        self.assertEqual(row['login'], tok('EMAIL', 'portal@cliente.com.br'))
        [row] = self._read(self.user, ['name'])
        self.assertEqual(row['name'], 'Vera Vendedora')

    def test_contact_address_tokenized(self):
        self.person.write({'street': 'Rua das Flores 10', 'zip': '13000-000'})
        [row] = self._read(self.person, ['contact_address'])
        self.assertTrue(row['contact_address'].startswith('ADDR#'))
        [row] = self._read(self.person, ['contact_address', 'name'], external=True)
        self.assertNotIn('contact_address', row)

    def test_kinds_login_place_of_birth(self):
        from ..tools.records import field_kind
        self.assertEqual(field_kind('login', 'a@b.com'), 'EMAIL')
        self.assertEqual(field_kind('place_of_birth', 'Campinas'), 'ADDR')
        self.assertEqual(field_kind('email_address', 'a@b.com'), 'EMAIL')
        self.assertEqual(field_kind('contact_address', 'Rua X'), 'ADDR')
        self.assertEqual(field_kind('birthday', '2000-01-01'), 'DATE')

    def test_tracking_value_partner_name_tokenized(self):
        self._require('mail.tracking.value')
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
        rows = sorted(self._read(values, fields, env=self.env), key=lambda r: r['id'])
        self.assertEqual(rows[0]['old_value_char'], 'ACME Ltda')
        self.assertEqual(rows[0]['new_value_char'], tok('NAME', 'Maria Pessoa'))
        self.assertEqual(rows[1]['new_value_char'], tok('EMAIL', 'maria@cliente.com.br'))
        external = self._read(values, fields, external=True, env=self.env)
        self.assertNotIn('cliente.com.br', json.dumps(external))

    def test_pairs_name_search(self):
        pairs = self.uenv['res.partner'].name_search('Maria Pessoa')
        masked = self._masker().pairs('res.partner', pairs)
        self.assertIn([self.person.id, tok('NAME', 'Maria Pessoa')], [list(p) for p in masked])
        self.assertNotIn('Maria Pessoa', json.dumps(masked))

    def test_web_read_nested_tokenized(self):
        rows = self.uenv['res.partner'].browse(self.child.ids).web_read(
            {'name': {}, 'parent_id': {'fields': {'display_name': {}}}}
        )
        [row] = self._masker().rows('res.partner', rows)
        self.assertEqual(row['parent_id'], {'id': self.person.id, 'display_name': tok('NAME', 'Maria Pessoa')})
        self.assertEqual(row['name'], tok('NAME', 'Filho Contato'))

    def test_many2one_portal_user_tokenized(self):
        portal = new_test_user(
            self.env, login='portal2@cliente.com.br', name='Paulo Portal', groups='base.group_portal'
        )
        self.person.user_id = portal
        self.company.user_id = self.user
        rows = sorted(self._read(self.person | self.company, ['user_id']), key=lambda r: r['id'])
        self.assertEqual(list(rows[0]['user_id']), [portal.id, tok('NAME', 'Paulo Portal')])
        self.assertEqual(list(rows[1]['user_id']), [self.user.id, 'Vera Vendedora'])
        groups = self._group('res.partner', [('id', '=', self.person.id)], ['user_id'])
        self.assertEqual(list(groups[0]['user_id']), [portal.id, tok('NAME', 'Paulo Portal')])

    def test_read_group_unknown_key_dropped(self):
        [group] = self._masker().groups('res.partner', [], [], [{'weird': 'Maria Pessoa', '__count': 1}])
        self.assertNotIn('weird', group)
        self.assertEqual(group['__count'], 1)

    def test_read_group_count_survives(self):
        [group] = self._group(
            'res.partner', [('id', '=', self.person.id)], ['is_company', 'city'], ['__count']
        )
        self.assertEqual(group['__count'], 1)
        [group] = self._masker().groups('res.partner', [], [], [{'__count': ['x'], '__fold': 'y'}])
        self.assertNotIn('__count', group)
        self.assertNotIn('__fold', group)

    def test_mask_label(self):
        masker = self._masker()
        self.assertEqual(
            masker.mask_label([self.person.id, 'Maria Pessoa']),
            [self.person.id, tok('NAME', 'Maria Pessoa')],
        )
        self.assertEqual(list(masker.mask_label([self.company.id, 'ACME Ltda'])), [self.company.id, 'ACME Ltda'])
        self.assertEqual(
            self._masker(external=True).mask_label([self.person.id, 'Maria Pessoa']),
            [self.person.id, 'Maria Pessoa'],
        )

    # -- fix round 1 ----------------------------------------------------
    def test_group_related_person_name_tokenized(self):
        domain = [('id', 'in', (self.person | self.company).ids)]
        groups = self._group('res.partner', domain, ['commercial_company_name'])
        labels = {g['commercial_company_name'] for g in groups}
        self.assertEqual(labels, {tok('NAME', 'Maria Pessoa'), 'ACME Ltda'})
        self.assertNotIn('Maria Pessoa', json.dumps(groups, default=str))
        [group] = self._group(
            'res.partner', [('id', '=', self.person.id)], ['is_company'],
            ['commercial_company_name:array_agg'],
        )
        self.assertEqual(group['commercial_company_name:array_agg'], [tok('NAME', 'Maria Pessoa')])

    def test_group_users_name_tokenized(self):
        portal = new_test_user(
            self.env, login='portal3@cliente.com.br', name='Pedro Portal', groups='base.group_portal'
        )
        groups = self._masker(env=self.env).groups(
            'res.users', ['name'], [],
            self.env['res.users'].formatted_read_group(
                [('id', 'in', [portal.id, self.user.id])], ['name'], []
            ),
        )
        labels = {g['name'] for g in groups}
        self.assertEqual(labels, {tok('NAME', 'Pedro Portal'), 'Vera Vendedora'})

    def test_person_without_company_evidence_masked(self):
        Partner = self.env['res.partner']
        foreign = Partner.create({'name': 'John Foreign', 'vat': 'DE123456789'})
        plain = Partner.create({'name': 'Plain Person'})
        bad_cnpj = Partner.create({'name': 'Bad Cnpj', 'vat': '11.222.333/0001-00'})
        rows = {r['id']: r['name'] for r in self._read(foreign | plain | bad_cnpj | self.company, ['name'])}
        self.assertEqual(rows[foreign.id], tok('NAME', 'John Foreign'))
        self.assertEqual(rows[plain.id], tok('NAME', 'Plain Person'))
        self.assertEqual(rows[bad_cnpj.id], tok('NAME', 'Bad Cnpj'))
        self.assertEqual(rows[self.company.id], 'ACME Ltda')

    def test_remask_case_and_whitespace_insensitive(self):
        pii = self.uenv['itbr.ai.pii']
        token = self.uenv['itbr.ai.pii.token']._emit('NAME', 'João Silva')
        for text in ('JOÃO SILVA', 'joão silva', 'João\nSilva', 'João   Silva'):
            self.assertEqual(pii._mask_text(f'Fale com {text}.'), f'Fale com {token}.')
        self.assertEqual(pii._mask_text('JoãoSilva'), 'JoãoSilva')

    def test_mask_text_does_not_touch(self):
        pii = self.uenv['itbr.ai.pii']
        Token = type(self.uenv['itbr.ai.pii.token'])
        token = self.uenv['itbr.ai.pii.token']._emit('NAME', 'João Silva')
        seen = set()
        with patch.object(Token, '_touch', autospec=True) as touch:
            pii._mask_text('Fale com João Silva', seen=seen)
            pii._mask_text('Fale com João Silva')
            touch.assert_not_called()
            pii._mask_any(['João Silva', {'a': 'João Silva'}])
            self.assertEqual(touch.call_count, 1)
            self.assertEqual(list(touch.call_args.args[1]), [token])
            pii._mask_any(['João Silva'], touch=False)
            self.assertEqual(touch.call_count, 1)
        self.assertEqual(seen, {token})

    def test_group_name_masked_when_lookup_hits_cap(self):
        from ..tools import records
        Partner = self.env['res.partner']
        # the person is the oldest, so the default order (id desc) puts it past the cap
        Partner.create({'name': 'Mesmo Nome'})
        Partner.create([
            {'name': 'Mesmo Nome', 'vat': '11.222.333/0001-81'},
            {'name': 'Mesmo Nome', 'vat': '11.222.333/0001-81'},
        ])
        with patch.object(records, 'NAME_LOOKUP_CAP', 2):
            self.assertEqual(self._masker().mask_name('Mesmo Nome'), tok('NAME', 'Mesmo Nome'))

    def _custom_field(self, name, ttype):
        self.env['ir.model.fields'].create({
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'name': name,
            'field_description': name,
            'ttype': ttype,
        })

    def test_blocked_numeric_aggregate_dropped(self):
        self._custom_field('x_salary', 'float')
        self.assertEqual(self._masker().level('res.partner', 'x_salary'), 'block')
        self.person.x_salary = 9000.0
        for external in (False, True):
            [group] = self._group(
                'res.partner', [('id', '=', self.person.id)], ['city'],
                ['x_salary:max', 'x_salary:sum', '__count'], external=external,
            )
            self.assertNotIn('x_salary:max', group)
            self.assertNotIn('x_salary:sum', group)
            self.assertEqual(group['__count'], 1)

    def test_redact_persons_for_external_sessions(self):
        before = self.Token.sudo().search_count([])
        masker = self.uenv['itbr.ai.pii']._masker(external=True, redact_persons=True)
        rows = {
            row['id']: row for row in masker.rows('res.partner', self.uenv['res.partner'].search_read(
                [('id', 'in', (self.person | self.company | self.child | self.user.partner_id).ids)],
                ['name', 'display_name', 'vat', 'parent_id', 'city'],
            ))
        }
        person = rows[self.person.id]
        self.assertEqual(person['name'], '[removido]')
        self.assertEqual(person['display_name'], '[removido]')
        self.assertNotIn('vat', person)
        self.assertEqual(person['city'], 'Campinas')
        self.assertEqual(rows[self.child.id]['parent_id'], [self.person.id, '[removido]'])
        self.assertEqual(rows[self.company.id]['name'], 'ACME Ltda')
        self.assertEqual(rows[self.user.partner_id.id]['name'], 'Vera Vendedora')
        groups = masker.groups(
            'res.partner', ['parent_id'], ['__count'],
            self.uenv['res.partner'].formatted_read_group(
                [('id', '=', self.child.id)], ['parent_id'], ['__count']
            ),
        )
        self.assertEqual(list(groups[0]['parent_id']), [self.person.id, '[removido]'])
        self.assertEqual(masker.mask_name('Maria Pessoa'), '[removido]')
        self.assertNotIn('Maria Pessoa', json.dumps([rows, groups], default=str))
        self.assertEqual(self.Token.sudo().search_count([]), before)
        # MCP-style external callers keep names readable
        [row] = self._read(self.person, ['name'], external=True)
        self.assertEqual(row['name'], 'Maria Pessoa')
