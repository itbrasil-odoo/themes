from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.itbr_muk_ai_pii.models.ir_model_fields import classify_field


@tagged('post_install', '-at_install')
class TestExposure(TransactionCase):
    def _exposure(self, model, name):
        field = self.env['ir.model.fields']._get(model, name)
        return field.ai_exposure

    def test_vat_tokenized(self):
        self.assertEqual(self._exposure('res.partner', 'vat'), 'tokenize')

    def test_email_tokenized(self):
        self.assertEqual(self._exposure('res.partner', 'email'), 'tokenize')

    def test_city_allowed(self):
        self.assertEqual(self._exposure('res.partner', 'city'), 'allow')

    def test_password_blocked(self):
        self.assertEqual(self._exposure('res.users', 'password'), 'block')

    def test_bank_account_blocked(self):
        self.assertEqual(self._exposure('res.partner.bank', 'acc_number'), 'block')

    def test_login_tokenized_on_users_only(self):
        self.assertEqual(self._exposure('res.users', 'login'), 'tokenize')

    def test_new_field_classified(self):
        field = self.env['ir.model.fields'].create({
            'name': 'x_cpf_responsavel',
            'model_id': self.env.ref('base.model_res_partner').id,
            'ttype': 'char',
            'field_description': 'CPF responsável',
            'state': 'manual',
        })
        self.assertEqual(field.ai_exposure_auto, 'tokenize')
        self.assertEqual(field.ai_exposure, 'tokenize')
        self.assertEqual(
            self.env['ir.model.fields']._ai_exposure_map('res.partner')['x_cpf_responsavel'],
            'tokenize',
        )

    def test_override_survives_update(self):
        field = self.env['ir.model.fields']._get('res.partner', 'email')
        field.ai_exposure_override = 'allow'
        self.assertEqual(field.ai_exposure, 'allow')
        self.assertEqual(self.env['ir.model.fields']._ai_exposure_map('res.partner')['email'], 'allow')
        self.env.add_to_compute(field._fields['ai_exposure_auto'], field)
        field.flush_recordset(['ai_exposure_auto', 'ai_exposure'])
        self.assertEqual(field.ai_exposure_override, 'allow')
        self.assertEqual(field.ai_exposure_auto, 'tokenize')
        self.assertEqual(field.ai_exposure, 'allow')

    def test_search_by_effective_exposure(self):
        field = self.env['ir.model.fields']._get('res.partner', 'city')
        field.ai_exposure_override = 'block'
        found = self.env['ir.model.fields'].search([('ai_exposure', '=', 'block'), ('id', '=', field.id)])
        self.assertEqual(found, field)

    def test_map(self):
        self.assertEqual(self.env['ir.model.fields']._ai_exposure_map('res.partner')['vat'], 'tokenize')

    def test_name_parts_tokenized(self):
        for name in (
            'x_responsavel_cpf', 'x_cliente_email', 'x_telefone',
            'x_studio_celular_contato', 'x_data_nascimento', 'email_cc',
            'phone_sanitized', 'street_number', 'x_cep', 'x_endereco', 'x_rua',
        ):
            self.assertEqual(classify_field('res.partner', name, 'char'), 'tokenize', name)

    def test_business_fields_allowed(self):
        for name in ('name', 'ref', 'amount_total', 'partner_id', 'website', 'city', 'state_id'):
            self.assertEqual(classify_field('sale.order', name, 'char'), 'allow', name)

    def test_token_last_part_blocked(self):
        for name in ('access_token', 'accesstoken', 'authtoken', 'token', 'x_api_token'):
            self.assertEqual(classify_field('res.partner', name, 'char'), 'block', name)
        self.assertEqual(classify_field('res.partner', 'token_count', 'integer'), 'allow')

    def test_exact_rules_stay_exact(self):
        self.assertEqual(classify_field('res.partner', 'vat', 'char'), 'tokenize')
        self.assertEqual(classify_field('res.partner', 'x_vat_note', 'char'), 'allow')
        self.assertEqual(classify_field('res.partner', 'login', 'char'), 'allow')

    def test_override_requires_system(self):
        field = self.env['ir.model.fields']._get('res.partner', 'vat')
        manager = new_test_user(self.env, login='pii_erp_manager', groups='base.group_erp_manager')
        with self.assertRaises(AccessError):
            field.with_user(manager).ai_exposure_override = 'allow'
        admin = new_test_user(self.env, login='pii_system', groups='base.group_system')
        field.with_user(admin).ai_exposure_override = 'allow'
        self.assertEqual(field.ai_exposure, 'allow')

    def test_map_null_falls_back_to_classifier(self):
        field = self.env['ir.model.fields']._get('res.partner', 'vat')
        field.flush_recordset()
        self.env.cr.execute('UPDATE ir_model_fields SET ai_exposure = NULL WHERE id = %s', [field.id])
        self.env.registry.clear_cache()
        self.assertEqual(self.env['ir.model.fields']._ai_exposure_map('res.partner')['vat'], 'tokenize')

    def test_tokenize_only_text_and_date_types(self):
        self.assertEqual(classify_field('ir.mail_server', 'max_email_size', 'integer'), 'allow')
        self.assertEqual(classify_field('res.company', 'hr_presence_control_email', 'boolean'), 'allow')
        self.assertEqual(classify_field('hr.employee', 'country_of_birth', 'many2one'), 'allow')
        self.assertEqual(classify_field('res.partner', 'email', 'char'), 'tokenize')
        self.assertEqual(classify_field('res.partner', 'x_data_nascimento', 'date'), 'tokenize')
        self.assertEqual(classify_field('res.partner', 'x_nascimento_hora', 'datetime'), 'tokenize')
        self.assertEqual(classify_field('res.partner', 'x_nota_email', 'html'), 'tokenize')
        self.assertEqual(classify_field('res.partner', 'x_emails', 'text'), 'tokenize')
        self.assertEqual(self._exposure('res.partner', 'email'), 'tokenize')

    def test_block_ignores_type(self):
        self.assertEqual(classify_field('res.partner', 'bank_count', 'integer'), 'block')
        self.assertEqual(classify_field('res.partner', 'private_flag', 'boolean'), 'block')
