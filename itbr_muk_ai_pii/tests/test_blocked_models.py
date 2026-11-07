import json

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestBlockedModels(TransactionCase):
    def _call(self, name, arguments):
        return self.env['muk_mcp.tool']._call(name, arguments, self.env)

    def _set_blocked(self, value):
        self.env['ir.config_parameter'].sudo().set_param(
            'itbr_muk_ai_pii.blocked_models', value
        )

    def test_blocked_model_refused(self):
        with self.assertRaises(AccessError):
            self._call('search_read', {'model': 'res.partner.bank'})

    def test_error_text_matches_access_module(self):
        with self.assertRaises(AccessError) as cm:
            self._call('search_read', {'model': 'res.partner.bank'})
        self.assertIn(
            "Model 'res.partner.bank' is not accessible via MCP.", str(cm.exception)
        )

    def test_list_models_hides_blocked(self):
        text, _info = self._call('list_models', {'search': 'res.partner', 'limit': 500})
        names = {row['model'] for row in json.loads(text)}
        self.assertIn('res.partner', names)
        self.assertNotIn('res.partner.bank', names)

    def test_unblocking_makes_readable(self):
        self._set_blocked('hr.payslip')
        self._call('search_read', {'model': 'res.partner.bank'})
        text, _info = self._call('list_models', {'search': 'res.partner.bank'})
        self.assertIn('res.partner.bank', {r['model'] for r in json.loads(text)})

    def test_unknown_names_ignored(self):
        self._set_blocked('no.such.model, res.partner.bank')
        blocked = self.env['muk_mcp.mixin']._itbr_pii_blocked_models()
        self.assertEqual(blocked, frozenset({'res.partner.bank'}))


@tagged('post_install', '-at_install')
class TestBlockedReachThrough(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Plain Co'})
        cls.bank = cls.env['res.partner.bank'].create(
            {'acc_number': 'XSECRET1', 'partner_id': cls.partner.id}
        )
        Attachment = cls.env['ir.attachment']
        cls.att_bank = Attachment.create(
            {'name': 'bank.txt', 'raw': b'x', 'res_model': 'res.partner.bank',
             'res_id': cls.bank.id}
        )
        cls.att_partner = Attachment.create(
            {'name': 'partner.txt', 'raw': b'x', 'res_model': 'res.partner',
             'res_id': cls.partner.id}
        )
        cls.msg_bank = cls.env['mail.message'].create(
            {'model': 'res.partner.bank', 'res_id': cls.bank.id, 'body': 'bankmsg',
             'message_type': 'comment'}
        )
        cls.msg_partner = cls.partner.message_post(body='partnermsg')

    def _call(self, name, arguments):
        return self.env['muk_mcp.tool']._call(name, arguments, self.env)

    def test_read_resource_blocked_attachment(self):
        with self.assertRaises(AccessError):
            self._call('read_resource', {'uri': f'odoo://attachment/{self.att_bank.id}'})

    def test_export_relational_path(self):
        with self.assertRaises(AccessError):
            self._call('export_records', {
                'model': 'res.partner',
                'fields': ['name', 'bank_ids/acc_number'],
                'ids': [self.partner.id],
            })

    def test_domain_path(self):
        with self.assertRaises(AccessError):
            self._call('search_read', {
                'model': 'res.partner',
                'domain': [('bank_ids.acc_number', '=', 'x')],
            })

    def _ids(self, model, domain):
        text, _info = self._call('search_read', {
            'model': model, 'domain': domain, 'fields': ['id'], 'limit': 500,
        })
        data = json.loads(text)
        rows = data['records'] if isinstance(data, dict) else data
        return {r['id'] for r in rows}

    def test_attachment_listing_filtered(self):
        ids = self._ids('ir.attachment', [])
        self.assertNotIn(self.att_bank.id, ids)
        self.assertIn(self.att_partner.id, ids)

    def test_message_listing_filtered(self):
        ids = self._ids('mail.message', [])
        self.assertNotIn(self.msg_bank.id, ids)
        self.assertIn(self.msg_partner.id, ids)
