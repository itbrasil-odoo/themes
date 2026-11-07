import os
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tools import config

from odoo.addons.muk_ai.tests.common import AITestCommon

REASON = (
    'This document may contain personal data (CPF, address, name) '
    'that goes to the AI provider without masking.'
)


class TestDocuments(AITestCommon):
    def setUp(self):
        super().setUp()
        env = {k: v for k, v in os.environ.items() if k != 'ODOO_AI_PII_KEY'}
        env['ODOO_AI_PII_KEY'] = 'test-key'
        env_patch = patch.dict(os.environ, env, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        options = {k: v for k, v in config.options.items() if k != 'ai_pii_key'}
        conf_patch = patch.dict(config.options, options, clear=True)
        conf_patch.start()
        self.addCleanup(conf_patch.stop)
        self.env['ir.config_parameter'].sudo().set_param('itbr_muk_ai_pii.enabled', 'True')
        self.report = self.env['ir.actions.report'].create({
            'name': 'Partner card',
            'model': 'res.partner',
            'report_type': 'qweb-pdf',
            'report_name': 'itbr_muk_ai_pii.test_partner_card',
        })
        self.partner = self.env['res.partner'].create({'name': 'Plain Co'})
        self.Approval = self.env['muk_ai.approval']

    def _print(self, ref=None):
        return self.Approval._assess_risk(
            'print_report', {'report_ref': ref or self.report.report_name, 'ids': [self.partner.id]}
        )

    def test_print_report_pauses_with_reason(self):
        risk = self._print()
        self.assertEqual(risk['model'], 'res.partner')
        self.assertEqual(risk['reason'], REASON)
        self.assertEqual(risk['tool'], 'print_report')
        self.assertEqual(risk['signature'], self.Approval._signature('print_report', 'res.partner'))

    def test_report_reference_by_id_and_xmlid(self):
        self.assertEqual(self._print(str(self.report.id))['model'], 'res.partner')
        self.env['ir.model.data'].create({
            'module': 'itbr_muk_ai_pii', 'name': 'test_partner_card_xmlid',
            'model': 'ir.actions.report', 'res_id': self.report.id,
        })
        self.assertEqual(
            self._print('itbr_muk_ai_pii.test_partner_card_xmlid')['model'], 'res.partner'
        )

    def test_read_resource_record_field_pauses(self):
        risk = self.Approval._assess_risk(
            'read_resource', {'uri': f'odoo://record/res.partner/{self.partner.id}/image_1920'}
        )
        self.assertEqual(risk['model'], 'res.partner')
        self.assertEqual(risk['reason'], REASON)

    def test_read_resource_attachment_pauses(self):
        att = self.env['ir.attachment'].create({'name': 'a.txt', 'raw': b'x'})
        risk = self.Approval._assess_risk('read_resource', {'uri': f'odoo://attachment/{att.id}'})
        self.assertEqual(risk['model'], 'ir.attachment')
        self.assertEqual(risk['reason'], REASON)

    def test_other_tools_not_affected(self):
        self.assertFalse(self.Approval._assess_risk('search_read', {'model': 'res.partner'}))

    def test_disabled_does_not_pause(self):
        self.env['ir.config_parameter'].sudo().set_param('itbr_muk_ai_pii.enabled', 'False')
        self.assertFalse(self._print())

    def test_approved_for_session_lets_same_model_pass(self):
        session = self.env['muk_ai.session'].create({'name': 'docs'})
        args = {'report_ref': self.report.report_name, 'ids': [self.partner.id]}
        gate = session._check_approval_gate('print_report', args)
        self.assertEqual(gate['action'], 'pause')
        session.approved_signatures = [gate['risk']['signature']]
        again = session._check_approval_gate('print_report', args)
        self.assertEqual(again['action'], 'auto_approved')

    def test_blocked_binary_field_refused(self):
        employee = self.env['hr.employee'].create({'name': 'Zed'}) if 'hr.employee' in self.env else None
        if employee is None:
            self.skipTest('hr not installed')
        exposure = self.env['ir.model.fields']._ai_exposure_map('hr.employee')
        blocked = [n for n, f in employee._fields.items()
                   if f.type == 'binary' and exposure.get(n) == 'block']
        self.assertTrue(blocked)
        with self.assertRaises(AccessError):
            self.env['muk_mcp.mixin']._resolve_resource_target(
                f'odoo://record/hr.employee/{employee.id}/{blocked[0]}'
            )

    def test_blocked_binary_field_refused_synthetic(self):
        # image_1920 on res.partner is not blocked; force the exposure to block
        field = self.env['ir.model.fields']._get('res.partner', 'image_1920')
        field.sudo().write({'ai_exposure_override': 'block'})
        with self.assertRaises(AccessError):
            self.env['muk_mcp.mixin']._resolve_resource_target(
                f'odoo://record/res.partner/{self.partner.id}/image_1920'
            )

    def test_session_and_token_models_always_blocked(self):
        self.env['ir.config_parameter'].sudo().set_param('itbr_muk_ai_pii.blocked_models', '')
        for model in ('muk_ai.session.event', 'itbr.muk_ai.pii.token', 'muk_ai.session'):
            with self.assertRaises(AccessError, msg=model):
                self.env['muk_mcp.tool']._call('search_read', {'model': model}, self.env)
        import json
        text, _i = self.env['muk_mcp.tool']._call('list_models', {'limit': 1000}, self.env)
        names = {r['model'] for r in json.loads(text)}
        self.assertFalse(names & {'muk_ai.session.event', 'itbr.muk_ai.pii.token', 'muk_ai.session'})

    def test_attachment_signed_by_res_model(self):
        Att = self.env['ir.attachment']
        a1 = Att.create({'name': 'a', 'raw': b'x', 'res_model': 'res.partner', 'res_id': self.partner.id})
        a2 = Att.create({'name': 'b', 'raw': b'x', 'res_model': 'res.partner', 'res_id': self.partner.id})
        a3 = Att.create({'name': 'c', 'raw': b'x', 'res_model': 'res.company', 'res_id': self.env.company.id})
        session = self.env['muk_ai.session'].create({'name': 'att'})
        gate = session._check_approval_gate('read_resource', {'uri': f'odoo://attachment/{a1.id}'})
        self.assertEqual(gate['risk']['model'], 'res.partner')
        session.approved_signatures = [gate['risk']['signature']]
        self.assertEqual(
            session._check_approval_gate('read_resource', {'uri': f'odoo://attachment/{a2.id}'})['action'],
            'auto_approved')
        self.assertEqual(
            session._check_approval_gate('read_resource', {'uri': f'odoo://attachment/{a3.id}'})['action'],
            'pause')

    def test_signature_of_one_model_does_not_pass_another(self):
        session = self.env['muk_ai.session'].create({'name': 'sig'})
        session.approved_signatures = [self.Approval._signature('print_report', 'res.company')]
        gate = session._check_approval_gate(
            'print_report', {'report_ref': self.report.report_name, 'ids': [self.partner.id]})
        self.assertEqual(gate['action'], 'pause')

    def test_non_string_uri_does_not_crash(self):
        for uri in (None, 5, ['x']):
            self.assertFalse(self.Approval._assess_risk('read_resource', {'uri': uri}).get('model'))

    def test_blocked_field_attachment_refused(self):
        field = self.env['ir.model.fields']._get('res.partner', 'image_1920')
        field.sudo().write({'ai_exposure_override': 'block'})
        att = self.env['ir.attachment'].sudo().create({
            'name': 'img', 'raw': b'x', 'res_model': 'res.partner',
            'res_id': self.partner.id, 'res_field': 'image_1920'})
        with self.assertRaises(AccessError):
            self.env['muk_mcp.mixin']._resolve_resource_target(f'odoo://attachment/{att.id}')
