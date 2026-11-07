from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

from odoo.orm.models import regex_field_agg

from odoo.addons.muk_mcp.tools.parser import coerce_json_value

from odoo.addons.muk_mcp.tools.uri import parse_uri

from ..tools.records import Masker

# Chat events and the token store hold real values, so no tool may reach them
ALWAYS_BLOCKED_MODELS = frozenset({
    'muk_ai.session', 'muk_ai.session.event', 'itbr.muk_ai.pii.token',
})
SESSION_KEY = 'itbr_pii_session_id'
# read-like methods reachable by call_method whose results are masked here;
# other results are left to the detector at the provider boundary
GROUP_METHODS = frozenset({'read_group', 'formatted_read_group', 'web_read_group'})
READ_METHODS = frozenset({
    'read', 'search_read', 'web_read', 'web_search_read', 'name_search',
    'read_group', 'formatted_read_group', 'web_read_group', 'web_save',
})


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
        names |= ALWAYS_BLOCKED_MODELS
        return frozenset(name for name in names if name in self.env)

    @api.model
    def _resolve_model(self, model):
        if model in self._itbr_pii_blocked_models():
            raise AccessError(
                _('Model %(model)r is not accessible via MCP.', model=model)
            )
        return super()._resolve_model(model)

    @api.model
    def _resolve_resource_target(self, uri):
        """Refuse a record binary field the exposure rules block (e.g. employee photos)."""
        kind, params = (parse_uri(uri) if isinstance(uri, str) else None) or (None, {})
        model = field = None
        if kind == 'record_field':
            model, field = params['model'], params['field']
        elif kind == 'attachment':
            attachment = self.env['ir.attachment'].sudo().browse(params['attachment_id']).exists()
            model, field = attachment.res_model, attachment.res_field
        if model and (
            model in self._itbr_pii_blocked_models()
            or (
                field
                and model in self.env
                and self.env['ir.model.fields']._ai_exposure_map(model).get(field) == 'block'
            )
        ):
            raise AccessError(
                _('Model %(model)r is not accessible via MCP.', model=model)
            )
        return super()._resolve_resource_target(uri)

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
        """Leave blocked fields out of exports, and tokenized ones for external clients."""
        masker = self._itbr_pii_masker()
        fields = [path for path in fields or [] if self._itbr_pii_export_path_ok(masker, model, path)]
        return super()._mcp_export_records(
            model, fields, ids=ids, domain=domain, format=format, limit=limit,
            order=order, delivery=delivery,
        )

    @api.model
    def _mcp_get_messages(self, model, id, limit=20):
        messages = super()._mcp_get_messages(model, id, limit=limit)
        return self._itbr_pii_masker().rows('mail.message', messages)

    @api.model
    def _mcp_call_method(self, model, method, ids=None, args=None, kwargs=None):
        if method in GROUP_METHODS:
            self._itbr_pii_check_group_keys(method, args, kwargs)
        result = super()._mcp_call_method(model, method, ids=ids, args=args, kwargs=kwargs)
        if method not in READ_METHODS:
            return result
        return self._itbr_pii_mask_method_result(model, method, args, kwargs, result)

    @api.model
    def _itbr_pii_group_args(self, method, args, kwargs):
        """Return ``(groupby, specs)`` of a grouping method call."""
        positional = coerce_json_value(args) or []
        keyword = dict(coerce_json_value(kwargs) or {})

        def arg(name, index, default):
            return keyword.get(name, positional[index] if len(positional) > index else default)

        if method == 'read_group':
            groupby, specs = arg('groupby', 2, []), arg('fields', 1, [])
        else:
            groupby, specs = arg('groupby', 1, []), arg('aggregates', 2, [])
        groupby = [groupby] if isinstance(groupby, str) else list(groupby or [])
        return [str(g) for g in groupby], [str(spec) for spec in specs or []]

    @api.model
    def _itbr_pii_check_group_keys(self, method, args, kwargs):
        """Refuse aggregates whose result key would collide with a groupby or meta key.

        Such a key would carry aggregated values under a name the masker treats
        as a group label or a count.
        """
        groupby, specs = self._itbr_pii_group_args(method, args, kwargs)
        taken = set(groupby) | {g.split(':')[0] for g in groupby}
        for spec in specs:
            if method == 'read_group':
                if ':' not in spec:
                    continue  # a plain field name, no alias
                match = regex_field_agg.match(spec)
                key = match.group(1) if match else spec
            else:
                key = spec
                if key == '__count':
                    continue
            if key in taken or key.startswith('__'):
                raise UserError(_(
                    'Aggregate %(spec)r would be returned under a reserved or grouped name.',
                    spec=spec,
                ))

    @api.model
    def _itbr_pii_mask_method_result(self, model, method, args, kwargs, result):
        masker = self._itbr_pii_masker()
        if method == 'name_search':
            return masker.pairs(model, result or [])
        if method == 'web_search_read' and isinstance(result, dict):
            return {**result, 'records': masker.rows(model, result.get('records') or [])}
        positional = coerce_json_value(args) or []
        keyword = dict(coerce_json_value(kwargs) or {})

        def arg(name, index, default):
            return keyword.get(name, positional[index] if len(positional) > index else default)

        if method == 'read_group':
            groupby = arg('groupby', 2, [])
            groupby = [groupby] if isinstance(groupby, str) else list(groupby or [])
            # 'alias:agg(field)' -> key alias, field; 'field:agg' / 'field' -> key field
            aggregates = {}
            for spec in arg('fields', 1, []) or []:
                match = regex_field_agg.match(str(spec))
                if not match:
                    continue
                name, _func, fname = match.groups()
                if name not in groupby:
                    aggregates[name] = fname or name
            return masker.groups(model, groupby, aggregates, list(result or []))
        if method == 'formatted_read_group':
            groupby = list(arg('groupby', 1, []) or [])
            aggregates = list(arg('aggregates', 2, []) or [])
            return masker.groups(model, groupby, aggregates, list(result or []))
        if method == 'web_read_group' and isinstance(result, dict):
            groupby = list(arg('groupby', 1, []) or [])
            aggregates = list(arg('aggregates', 2, []) or [])
            return {**result, 'groups': masker.groups(model, groupby, aggregates, result.get('groups') or [])}
        if isinstance(result, list) and all(isinstance(row, dict) for row in result):
            return masker.rows(model, result)
        return result

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
            if not masker.visible(current, name):
                return False
            if not field.relational:
                return True
            current = field.comodel_name
        return True
