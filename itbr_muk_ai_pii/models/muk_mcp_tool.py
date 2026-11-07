from odoo import api, models

from .muk_mcp_mixin import SESSION_KEY


class MCPTool(models.Model):
    _inherit = 'muk_mcp.tool'

    @api.model
    def _call(self, name, arguments, env, enforce_scope=None):
        """Drop a chat session id passed by the caller in the tool ``context``.

        Only a chat puts it in the environment; an external MCP client claiming
        one would get a session's treatment (real values when tokens are off).
        """
        if isinstance(arguments, dict) and isinstance(arguments.get('context'), dict):
            arguments = {
                **arguments,
                'context': {k: v for k, v in arguments['context'].items() if k != SESSION_KEY},
            }
        return super()._call(name, arguments, env, enforce_scope)
