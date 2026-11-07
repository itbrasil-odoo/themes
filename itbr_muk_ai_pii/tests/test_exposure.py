from odoo.tests import tagged
from odoo.tests.common import TransactionCase


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
