from odoo import _, api, models

from odoo.addons.muk_mcp.tools.uri import parse_uri


class MukAiApproval(models.Model):
    """Ask the user before a document, which cannot be masked, goes to the AI."""

    _inherit = 'muk_ai.approval'

    @api.model
    def _assess_risk(self, tool_name, arguments):
        risk = super()._assess_risk(tool_name, arguments)
        if risk or tool_name not in ('print_report', 'read_resource'):
            return risk
        if not self.env['itbr.muk_ai.pii.token']._enabled():
            return risk
        if tool_name == 'print_report':
            report = self.env['muk_mcp.mixin']._resolve_report(arguments.get('report_ref') or '')
            model = report.model if report else ''
        else:
            kind, params = parse_uri(arguments.get('uri')) or (None, {})
            model = {'attachment': 'ir.attachment', 'record_field': (params or {}).get('model')}.get(kind, '')
        return {
            'tool': tool_name,
            'model': model or '',
            'ids': [],
            'method': '',
            'reason': _(
                'This document may contain personal data (CPF, address, name) '
                'that goes to the AI provider without masking.'
            ),
            'signature': self._signature(tool_name, model or ''),
        }
