from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.muk_ai.tests.common import AITestCommon

BLOCKED = {'web_search', 'web_fetch'}
PARAMS = (
    'itbr_muk_ai_guard.approve_all_writes',
    'itbr_muk_ai_guard.admin_only_approval_off',
    'itbr_muk_ai_guard.block_web',
)


@tagged('post_install', '-at_install')
class TestGuard(AITestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = new_test_user(
            cls.env, login='guard_employee', groups='base.group_user'
        )
        cls.admin = new_test_user(
            cls.env, login='guard_admin', groups='base.group_user,base.group_system'
        )
        cls.agent_off = cls.env['muk_ai.agent'].create(
            {'name': 'No approvals', 'approval_mode': 'off'}
        )

    def _session(self, user, **values):
        return (
            self.env['muk_ai.session'].with_user(user).create({'name': 'guard', **values})
        )

    def _switch_off(self, key):
        self.env['ir.config_parameter'].sudo().set_param(key, False)

    def _risk(self, tool='update_records'):
        return self.env['muk_ai.approval']._assess_risk(
            tool, {'model': 'res.partner.category', 'ids': [1], 'method': 'copy'}
        )

    # Defaults

    def test_installed_switched_on(self):
        params = self.env['ir.config_parameter'].sudo()
        for key in PARAMS:
            self.assertEqual(params.get_param(key), 'True', key)

    # Approval on every write

    def test_write_on_any_model_needs_approval(self):
        self.assertFalse(self.env['ir.model']._get('res.partner.category').ai_sensitive)
        for tool in (
            'create_records',
            'update_records',
            'delete_records',
            'call_method',
        ):
            self.assertTrue(self._risk(tool), tool)

    def test_read_does_not_need_approval(self):
        self.assertIsNone(self._risk('search_read'))

    def test_switched_off_only_sensitive_models_ask(self):
        self._switch_off('itbr_muk_ai_guard.approve_all_writes')
        self.assertIsNone(self._risk())

    # Approval cannot be switched off by non-admins

    def test_employee_cannot_get_approval_off_from_agent(self):
        session = self._session(self.employee, agent_id=self.agent_off.id)
        self.assertEqual(session._effective_approval_mode(), 'ask')

    def test_employee_cannot_get_approval_off_from_override(self):
        session = self._session(self.employee)
        session.sudo().override_approval_mode = 'off'
        self.assertEqual(session._effective_approval_mode(), 'ask')

    def test_employee_cannot_switch_approval_off(self):
        session = self._session(self.employee)
        with self.assertRaises(UserError):
            session.set_approval_mode('off')
        session.set_approval_mode('ask')
        self.assertEqual(session.override_approval_mode, 'ask')

    def test_admin_keeps_approval_off(self):
        session = self._session(self.admin, agent_id=self.agent_off.id)
        self.assertEqual(session._effective_approval_mode(), 'off')
        session.set_approval_mode('off')
        self.assertEqual(session.override_approval_mode, 'off')

    def test_switched_off_employee_may_turn_approval_off(self):
        self._switch_off('itbr_muk_ai_guard.admin_only_approval_off')
        session = self._session(self.employee, agent_id=self.agent_off.id)
        self.assertEqual(session._effective_approval_mode(), 'off')
        session.set_approval_mode('off')
        self.assertEqual(session.override_approval_mode, 'off')

    # No web access

    def test_web_tools_left_out_of_catalog(self):
        session = self._session(self.employee)
        tools = self.env['muk_mcp.tool'].sudo().get_tools(registry='odoo')
        self.assertTrue(BLOCKED & {tool['name'] for tool in tools})
        names = {entry['name'] for entry in session._get_filtered_catalog()}
        self.assertFalse(BLOCKED & names)

    def test_web_tool_call_refused(self):
        session = self._session(self.employee)
        with patch.object(type(self.env['muk_mcp.tool']), '_call', autospec=True) as call:
            output, ok = session._dispatch_tool_call(
                'web_fetch', {'url': 'https://example.com'}, 'c1'
            )
        self.assertFalse(ok)
        self.assertIn('error', output)
        call.assert_not_called()

    def test_native_web_search_off(self):
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Searcher', 'web_search': 'native'}
        )
        session = self._session(self.employee, agent_id=agent.id)
        self.assertIsNone(session._web_search_route())

    def test_switched_off_web_tools_come_back(self):
        self._switch_off('itbr_muk_ai_guard.block_web')
        session = self._session(self.employee)
        names = {entry['name'] for entry in session._get_filtered_catalog()}
        self.assertIn('web_fetch', names)

    # Settings

    def test_settings_round_trip(self):
        settings = self.env['res.config.settings'].create({})
        self.assertTrue(settings.itbr_muk_ai_guard_block_web)
        settings.itbr_muk_ai_guard_block_web = False
        settings.execute()
        self.assertFalse(
            self.env['ir.config_parameter'].sudo().get_param(
                'itbr_muk_ai_guard.block_web'
            )
        )
