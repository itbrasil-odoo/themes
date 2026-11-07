from odoo import _, api, models
from odoo.exceptions import AccessError

from ..tools.records import Masker

SESSION_KEY = 'itbr_pii_session_id'


class MCPMixin(models.AbstractModel):
    """Keep blocked models out of reach of the AI and mask personal data in results."""

    _inherit = 'muk_mcp.mixin'

    @api.model
    def _itbr_pii_blocked_models(self):
        """Return the blocked model names that exist in this registry."""
        value = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('itbr_muk_ai_pii.blocked_models', '')
        )
        names = {name.strip() for name in (value or '').split(',') if name.strip()}
        return frozenset(name for name in names if name in self.env)

    @api.model
    def _resolve_model(self, model):
        if model in self._itbr_pii_blocked_models():
            raise AccessError(
                _('Model %(model)r is not accessible via MCP.', model=model)
            )
        return super()._resolve_model(model)

    @api.model
    def _mcp_listable_model_names(self):
        listable = super()._mcp_listable_model_names()
        if listable is None:
            listable = set(self.env.registry)
        return set(listable) - self._itbr_pii_blocked_models()

    @api.model
    def _mcp_record_domain(self, model):
        """Hide records attached to a blocked model from attachment/message models."""
        domain = super()._mcp_record_domain(model)
        if model not in ('ir.attachment', 'mail.message', 'mail.activity'):
            return domain
        blocked = self._itbr_pii_blocked_models()
        if not blocked:
            return domain
        extra = [('res_model', 'not in', sorted(blocked))]
        if model == 'mail.message':
            extra = [('model', 'not in', sorted(blocked))]
        return list(domain) + extra if domain else extra

    # ----------------------------------------------------------
    # Personal data in results
    # ----------------------------------------------------------

    @api.model
    def _itbr_pii_session(self):
        """Return the chat session of the call, or an empty one for an external MCP client."""
        session_id = self.env.context.get(SESSION_KEY)
        Session = self.env['muk_ai.session'].sudo()
        if not isinstance(session_id, int) or isinstance(session_id, bool) or not session_id:
            return Session
        return Session.browse(session_id).exists()

    @api.model
    def _itbr_pii_masker(self):
        return Masker(self.env, self._itbr_pii_session())

    @api.model
    def _mcp_read(self, records, fields):
        masker = self._itbr_pii_masker()
        readable, links = masker.split_fields(records._name, fields)
        rows = masker.rows(records._name, super()._mcp_read(records, readable))
        for row in rows:
            row.update(dict.fromkeys(links, False))
        return rows

    @api.model
    def _mcp_read_group(
        self, model, groupby=None, aggregates=None, domain=None, limit=None, order=None
    ):
        groups = super()._mcp_read_group(
            model, groupby=groupby, aggregates=aggregates, domain=domain, limit=limit, order=order
        )
        return self._itbr_pii_masker().groups(model, groupby or [], aggregates or [], groups)

    @api.model
    def _mcp_describe_model(self, model, fields=None):
        result = super()._mcp_describe_model(model, fields=fields)
        masker = self._itbr_pii_masker()
        return {name: attrs for name, attrs in result.items() if masker.visible(model, name)}

    @api.model
    def _mcp_export_records(self, model, fields, ids=None, domain=None, format='csv',
                            limit=1000, order=None, delivery='inline'):
        """Leave blocked and tokenized fields out of exports.

        A file cannot be detokenized, so tokenized fields are dropped even in a
        chat session, as for an external MCP client.
        """
        masker = self._itbr_pii_masker()
        fields = [path for path in fields or [] if self._itbr_pii_export_path_ok(masker, model, path)]
        return super()._mcp_export_records(
            model, fields, ids=ids, domain=domain, format=format, limit=limit,
            order=order, delivery=delivery,
        )

    @api.model
    def _itbr_pii_export_path_ok(self, masker, model, path):
        current = model
        for name in str(path).split('/'):
            if name in ('id', '.id') or current not in self.env:
                return True
            field = self.env[current]._fields.get(name)
            if field is None:
                return True  # let the export report the unknown field
            if field.relational and field.comodel_name in masker.blocked:
                return True  # refused by _resolve_model, not dropped silently
            if masker.level(current, name) != 'allow':
                return False
            if not field.relational:
                return True
            current = field.comodel_name
        return True
