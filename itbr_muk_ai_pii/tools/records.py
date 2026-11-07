"""Mask the personal data of tool results before the AI provider reads them.

``block`` fields are dropped. ``tokenize`` fields become ``KIND#hex`` tokens of
the chat session, and so do the names of person partners (customers and
contacts), while the names of the team (internal users, employees) and of
companies stay readable. Without a session (external MCP client, which cannot
reveal tokens) ``tokenize`` fields are dropped and names stay real.
"""
import datetime
import numbers

from odoo import fields as odoo_fields

from .detector import document_kind, normalize

NAME_COPY_FIELDS = frozenset({'contact_name', 'partner_name', 'invoice_partner_display_name'})
PARTNER_NAME_FIELDS = frozenset({'name', 'display_name', 'complete_name'})
PARTNER = 'res.partner'


def _name_parts(name):
    name = (name or '').lower()
    for prefix in ('x_studio_', 'x_'):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name, name.split('_')


def field_kind(name, value):
    """Return the token kind of a tokenized field, by its name (and value for documents)."""
    name, parts = _name_parts(name)

    def has(prefixes, words=frozenset()):
        return any(p.startswith(prefixes) or p in words for p in parts)

    if has(('cnpj', 'cpf'), {'vat'}):
        return document_kind(value)
    if has(('email',)):
        return 'EMAIL'
    if has(('phone', 'mobile'), {'telefone', 'celular'}):
        return 'PHONE'
    if has(('street', 'zip'), {'cep', 'endereco', 'rua'}):
        return 'ADDR'
    if has(('birth',), {'nascimento'}):
        return 'DATE'
    if name in NAME_COPY_FIELDS or name.endswith('_partner_name'):
        return 'NAME'
    return 'DOC'


def _as_text(value):
    if isinstance(value, datetime.datetime):
        return odoo_fields.Datetime.to_string(value)
    if isinstance(value, datetime.date):
        return odoo_fields.Date.to_string(value)
    return str(value)


def _is_empty(value):
    return value is None or value is False or (isinstance(value, str) and not value.strip())


class Masker:
    """Mask rows of one tool call; caches exposure maps, person checks and tokens."""

    def __init__(self, env, session):
        self.env = env
        self.session = session
        self.store = env['itbr.muk_ai.pii.token']
        self.tokens = bool(session) and self.store._enabled()
        self.blocked = env['muk_mcp.mixin']._itbr_pii_blocked_models()
        self._exposure = {}
        self._persons = {}
        self._emitted = {}

    # -- classification -------------------------------------------------
    def exposure(self, model_name):
        if model_name not in self._exposure:
            self._exposure[model_name] = self.env['ir.model.fields'].sudo()._ai_exposure_map(
                model_name
            )
        return self._exposure[model_name]

    def level(self, model_name, name):
        """'block', 'tokenize' or 'allow' for one field; relations to blocked models block."""
        field = self.env[model_name]._fields.get(name)
        if field is not None and field.relational and field.comodel_name in self.blocked:
            return 'block'
        return self.exposure(model_name).get(name, 'allow')

    def visible(self, model_name, name):
        """Whether the field may be shown at all to this caller."""
        level = self.level(model_name, name)
        return level == 'allow' or (level == 'tokenize' and bool(self.session))

    def blocked_link(self, model_name, name):
        """Whether ``name`` is a Many2one to a blocked model (shown as ``False``, R15)."""
        field = self.env[model_name]._fields.get(name)
        return field is not None and field.type == 'many2one' and field.comodel_name in self.blocked

    def split_fields(self, model_name, names):
        """Return the fields to read and the Many2one fields to blocked models."""
        readable = [n for n in names if self.visible(model_name, n)]
        links = [n for n in names if self.blocked_link(model_name, n)]
        return readable, links

    # -- tokens ---------------------------------------------------------
    def emit(self, kind, value):
        if not self.tokens or _is_empty(value):
            return value
        if isinstance(value, (list, tuple)):
            return [self.emit(kind, v) for v in value]
        if isinstance(value, bool):
            return value
        text = _as_text(value)
        normalized = normalize(kind, text)
        key = (kind, normalized)
        if key not in self._emitted:
            self._emitted[key] = self.store._emit(kind, normalized, self.session)
        return self._emitted[key]

    def emit_field(self, name, value):
        if isinstance(value, (list, tuple)):
            return [self.emit_field(name, v) for v in value]
        if _is_empty(value) or isinstance(value, bool):
            return value
        return self.emit(field_kind(name, _as_text(value)), value)

    # -- people ---------------------------------------------------------
    def load_persons(self, ids):
        """Classify partner ids at once: person (masked) or company/team (readable)."""
        missing = {i for i in ids if isinstance(i, int) and i not in self._persons}
        if not missing or not self.tokens:
            return
        env = self.env(su=True, context={**self.env.context, 'active_test': False})
        partners = env[PARTNER].browse(sorted(missing)).exists()
        people = set(partners.filtered(lambda p: not p.is_company).ids)
        team = {
            user.partner_id.id
            for user in env['res.users'].search_fetch(
                [('partner_id', 'in', list(people)), ('share', '=', False)], ['partner_id']
            )
        }
        if 'hr.employee' in env and 'work_contact_id' in env['hr.employee']._fields:
            team |= {
                employee.work_contact_id.id
                for employee in env['hr.employee'].search_fetch(
                    [('work_contact_id', 'in', list(people))], ['work_contact_id']
                )
            }
        for pid in missing:
            self._persons[pid] = pid in people and pid not in team

    def is_person(self, pid):
        if not self.tokens or not isinstance(pid, int):
            return False
        self.load_persons([pid])
        return self._persons.get(pid, False)

    def mask_label(self, value):
        """``(id, label)`` of a partner: the label becomes ``NAME#`` for a person."""
        if isinstance(value, (list, tuple)) and len(value) == 2 and self.is_person(value[0]):
            return [value[0], self.emit('NAME', value[1])]
        return value

    # -- rows -----------------------------------------------------------
    def rows(self, model_name, rows):
        model_fields = self.env[model_name]._fields
        is_partner = model_name == PARTNER
        partner_m2o = {
            name for name, field in model_fields.items()
            if field.type == 'many2one' and field.comodel_name == PARTNER
        }
        if self.tokens:
            ids = set()
            for row in rows:
                if is_partner:
                    ids.add(row.get('id'))
                for name in partner_m2o.intersection(row):
                    if row[name]:
                        ids.add(row[name][0])
            self.load_persons(ids)
        result = []
        for row in rows:
            masked = {}
            for name, value in row.items():
                if name == 'id':
                    masked[name] = value
                    continue
                level = self.level(model_name, name)
                if level == 'block' or (level == 'tokenize' and not self.session):
                    if self.blocked_link(model_name, name):
                        masked[name] = False  # R15: the field exists, the link is hidden
                    continue
                if level == 'tokenize':
                    value = self.emit_field(name, value)
                elif name in partner_m2o and value:
                    value = self.mask_label(value)
                elif is_partner and name in PARTNER_NAME_FIELDS and self.is_person(row.get('id')):
                    value = self.emit('NAME', value)
                masked[name] = value
            result.append(masked)
        return result

    # -- read_group -----------------------------------------------------
    def spec(self, model_name, spec):
        """Resolve a groupby/aggregate spec to ``(level, model, field)`` of its last field.

        ``level`` adds ``'name'`` for a partner name: grouped values carry no id to
        tell a person from a company, so they are all tokenized.
        """
        path = spec.split(':')[0].split('.')
        model = model_name
        field = None
        for index, name in enumerate(path):
            field = self.env[model]._fields.get(name)
            if field is None:
                return 'allow', model, None
            level = self.level(model, name)
            if level != 'allow':
                return level, model, field
            if index < len(path) - 1:
                if not field.relational:
                    return 'allow', model, field
                model = field.comodel_name
        if model == PARTNER and field.name in PARTNER_NAME_FIELDS:
            return 'name', model, field
        return 'allow', model, field

    def groups(self, model_name, groupby, aggregates, groups):
        specs = {spec: self.spec(model_name, spec) for spec in groupby}
        aggs = {
            spec: self.spec(model_name, spec.split(':')[0])
            for spec in aggregates if spec != '__count'
        }
        if self.tokens:
            ids = set()
            for spec, (_level, _model, field) in specs.items():
                if field is not None and field.relational and field.comodel_name == PARTNER:
                    ids.update(g[spec][0] for g in groups if isinstance(g.get(spec), (list, tuple)))
            self.load_persons(ids)
        for group in groups:
            for spec, (level, _model, field) in specs.items():
                if spec not in group:
                    continue
                value = group[spec]
                if level == 'block' or (level == 'tokenize' and not self.session):
                    group[spec] = False
                    group.pop('__extra_domain', None)
                elif level == 'tokenize':
                    group[spec] = self.emit_field(field.name, value)
                    if self.tokens and '__extra_domain' in group:
                        if '.' in spec.split(':')[0]:
                            group.pop('__extra_domain')
                        else:
                            group['__extra_domain'] = self._mask_domain(
                                group['__extra_domain'], field.name
                            )
                elif level == 'name':
                    if self.tokens:
                        group[spec] = self.emit('NAME', value)
                        group.pop('__extra_domain', None)
                elif field is not None and field.relational and field.comodel_name == PARTNER:
                    group[spec] = self.mask_label(value)
            for spec, (level, _model, field) in aggs.items():
                if spec not in group:
                    continue
                value = group[spec]
                if isinstance(value, numbers.Number) and not isinstance(value, bool):
                    continue  # counts and sums carry no personal value
                if level == 'block' or (level == 'tokenize' and not self.session):
                    group.pop(spec)
                elif level == 'tokenize':
                    group[spec] = self.emit_field(field.name, value)
                elif level == 'name':
                    group[spec] = self.emit('NAME', value)
        return groups

    def _mask_domain(self, domain, name):
        masked = []
        for leaf in domain:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3 and leaf[0] == name:
                leaf = (leaf[0], leaf[1], self.emit_field(name, leaf[2]))
            masked.append(leaf)
        return masked


def mask_rows(env, model_name, rows, session):
    """Return ``rows`` of ``model_name`` with personal data masked for ``session``."""
    return Masker(env, session).rows(model_name, rows)
