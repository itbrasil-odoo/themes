from odoo import _, models
from odoo.exceptions import UserError

from .res_config_settings import ADMIN_ONLY_APPROVAL_OFF, BLOCK_WEB, guard_enabled

# Tools that reach the internet. A prompt planted in record data could make
# the agent send what it read to an outside URL.
WEB_TOOLS = frozenset({'web_search', 'web_fetch'})


class MukAISession(models.Model):
    _inherit = 'muk_ai.session'

    def _effective_approval_mode(self):
        mode = super()._effective_approval_mode()
        if (
            mode == 'off'
            and guard_enabled(self.env, ADMIN_ONLY_APPROVAL_OFF)
            and not (self and self.user_id.has_group('base.group_system'))
        ):
            return 'ask'
        return mode

    def set_approval_mode(self, mode):
        self.check_access('write')
        if (
            mode == 'off'
            and guard_enabled(self.env, ADMIN_ONLY_APPROVAL_OFF)
            and not self.env.user.has_group('base.group_system')
        ):
            raise UserError(_('Only administrators can turn off AI approvals.'))
        return super().set_approval_mode(mode)

    def _web_search_route(self):
        if guard_enabled(self.env, BLOCK_WEB):
            return None
        return super()._web_search_route()

    def _get_filtered_catalog(self):
        catalog = super()._get_filtered_catalog()
        if not guard_enabled(self.env, BLOCK_WEB):
            return catalog
        return [entry for entry in catalog if entry.get('name') not in WEB_TOOLS]

    def _dispatch_tool_call(self, name, arguments, call_id):
        if name in WEB_TOOLS and guard_enabled(self.env, BLOCK_WEB):
            return {'error': _('Tool %s is disabled in this database.', name)}, False
        return super()._dispatch_tool_call(name, arguments, call_id)
