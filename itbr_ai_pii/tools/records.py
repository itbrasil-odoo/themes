"""Mask the personal data of tool results before the AI provider reads them.

``block`` fields are dropped. ``tokenize`` fields become ``KIND#hex`` tokens of
the current user, and so do the names of person partners (customers and
contacts), while the names of the team (internal users, employees) and of
companies stay readable. Without a key the values go out as they are. For an
external caller (which cannot reveal tokens) ``tokenize`` fields are dropped,
no token is emitted and names stay real, unless ``redact_persons`` is set
(a livechat/portal/public requester, where the result reaches a third party):
then person names become ``[removido]`` while company and team names stay.
"""
import datetime
import numbers

from odoo import fields as odoo_fields

from .detector import document_kind, normalize, valid_cnpj

# What a person's name becomes for an external session (no token, no value)
REDACTED = '[removido]'

NAME_COPY_FIELDS = frozenset({'contact_name', 'partner_name', 'invoice_partner_display_name'})
PARTNER_NAME_FIELDS = frozenset({'name', 'display_name', 'complete_name'})
PARTNER = 'res.partner'
USERS = 'res.users'
PEOPLE_MODELS = (PARTNER, USERS)
# char field naming the record of a (model, res_id) pair -> the fields of that pair
RECORD_NAME_FIELDS = {'record_name': ('model', 'res_id'), 'res_name': ('res_model', 'res_id')}
# computed (not related) name fields that copy the name of a partner link
COMPUTED_NAME_LINKS = {('mail.followers', 'display_name'): ['partner_id']}
# group keys that are not values of a field; anything else unknown is dropped
# partners looked up per bare name; more than this and the name is masked
NAME_LOOKUP_CAP = 100
GROUP_META_KEYS = frozenset({'__extra_domain', '__domain', '__count', '__fold', '__context', '__offset'})
TRACKING = 'mail.tracking.value'
TRACKING_VALUES = {
    'old_value_char': 'old_value_integer', 'new_value_char': 'new_value_integer',
}
TRACKING_ALL = (
    'old_value_integer', 'old_value_float', 'old_value_char', 'old_value_text', 'old_value_datetime',
    'new_value_integer', 'new_value_float', 'new_value_char', 'new_value_text', 'new_value_datetime',
)


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
    if has(('email',)) or name == 'login':
        return 'EMAIL'
    if has(('phone', 'mobile'), {'telefone', 'celular'}):
        return 'PHONE'
    if has(('street', 'zip', 'address'), {'cep', 'endereco', 'rua'}):
        return 'ADDR'
    if has(('birth',), {'nascimento'}):
        # place of birth is a place, not a date
        return 'ADDR' if has((), {'place', 'local'}) else 'DATE'
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

    def __init__(self, env, external=False, redact_persons=False):
        self.env = env
        self.external = bool(external)
        self.store = env['itbr.ai.pii.token']
        self.tokens = not self.external and env['itbr.ai.pii']._tokens_available()
        self.redact = bool(
            self.external and redact_persons
            and env['ir.config_parameter'].sudo().get_bool('itbr_ai_pii.enabled', True)
        )
        # persons are told apart when their names are tokenized or redacted
        self.persons = self.tokens or self.redact
        self.blocked = env['itbr.ai.pii']._blocked_models()
        self._exposure = {}
        self._persons = {}
        self._shared_users = {}
        self._emitted = {}
        self._names = {}

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
        return level == 'allow' or (level == 'tokenize' and not self.external)

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
        if kind == 'NAME' and self.redact and not _is_empty(value) and not isinstance(value, bool):
            if isinstance(value, (list, tuple)):
                return [self.emit(kind, v) for v in value]
            return REDACTED
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
            self._emitted[key] = self.store._emit(kind, normalized)
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
        if not missing or not self.persons:
            return
        env = self.env(su=True, context={**self.env.context, 'active_test': False})
        partners = env[PARTNER].browse(sorted(missing)).exists()
        # Fail closed: only a valid CNPJ proves a company. Odoo 20 flags any
        # partner with a VAT as a company (a CPF or a foreign personal id too),
        # so is_company is no evidence; anyone else is a person.
        people = set(partners.filtered(lambda p: not valid_cnpj(p.vat or '')).ids)
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
        if not self.persons or not isinstance(pid, int):
            return False
        self.load_persons([pid])
        return self._persons.get(pid, False)

    def load_users(self, ids):
        """Classify user ids at once: portal/public users (``share``) are clients."""
        missing = {i for i in ids if isinstance(i, int) and i not in self._shared_users}
        if not missing or not self.persons:
            return
        users = self._sudo()[USERS].browse(sorted(missing)).exists()
        shared = set(users.filtered('share').ids)
        for uid in missing:
            self._shared_users[uid] = uid in shared

    def is_client_user(self, uid):
        if not self.persons or not isinstance(uid, int):
            return False
        self.load_users([uid])
        return self._shared_users.get(uid, False)

    def load_labels(self, comodel, ids):
        if comodel == PARTNER:
            self.load_persons(ids)
        elif comodel == USERS:
            self.load_users(ids)

    def mask_label(self, value, comodel=PARTNER):
        """``(id, label)`` of a partner or user: ``NAME#`` label for a person or portal user."""
        if not (isinstance(value, (list, tuple)) and len(value) == 2):
            return value
        masked = self.is_client_user(value[0]) if comodel == USERS else self.is_person(value[0])
        return [value[0], self.emit('NAME', value[1])] if masked else value

    def _sudo(self):
        return self.env(su=True, context={**self.env.context, 'active_test': False})

    @staticmethod
    def _partner_of(record):
        """The partner behind a res.partner or res.users record (empty otherwise)."""
        if record._name == USERS:
            return record.partner_id
        return record if record._name == PARTNER else record.browse()

    def _name_link(self, model_name, field):
        """Path to the partner/user whose name ``field`` copies, else ``None``.

        ``[]`` means the record itself (a partner or user name field).
        """
        if field is None:
            return None
        if model_name in PEOPLE_MODELS and field.name in PARTNER_NAME_FIELDS:
            return []
        if (model_name, field.name) in COMPUTED_NAME_LINKS:
            return COMPUTED_NAME_LINKS[(model_name, field.name)]
        if field.type not in ('char', 'text') or not field.related:
            return None
        related = field.related
        path = related.split('.') if isinstance(related, str) else list(related)
        target = self.env[model_name]
        for step in path[:-1]:
            sub = target._fields.get(step)
            if sub is None or not sub.relational:
                return None
            target = self.env[sub.comodel_name]
        if target._name in PEOPLE_MODELS and path[-1] in PARTNER_NAME_FIELDS:
            return path[:-1]
        return None

    def _row_actions(self, model_name, rows):
        """Per row id, the fields whose value names a person or carries a tracked value.

        Actions: ``('person', partner_id)``, ``('tokenize', field_name)``, ``('block',)``.
        Everything is read in one sudo pass over the rows.
        """
        if not self.persons and model_name != TRACKING:
            return {}
        model = self.env[model_name]
        keys = set().union(*rows) if rows else set()
        related = {}
        for name in keys:
            path = self._name_link(model_name, model._fields.get(name))
            # partner/user name fields of the record itself are handled apart
            if path:
                related[name] = path
        records_named = {
            name: pair for name, pair in RECORD_NAME_FIELDS.items()
            if name in keys and all(f in model._fields for f in pair)
        }
        self_named = model_name == USERS and keys & PARTNER_NAME_FIELDS
        tracking = model_name == TRACKING and keys & set(TRACKING_ALL)
        if not (related or records_named or self_named or tracking):
            return {}
        env = self._sudo()
        records = env[model_name].browse([r['id'] for r in rows if isinstance(r.get('id'), int)])
        actions = {}
        for record in records.exists():
            row_actions = actions.setdefault(record.id, {})
            for name, path in related.items():
                target = record
                for step in path:
                    target = target[step][:1]
                if partner := self._partner_of(target):
                    row_actions[name] = ('person', partner.id)
            for name, (model_field, id_field) in records_named.items():
                if record[model_field] in PEOPLE_MODELS and record[id_field]:
                    partner = self._partner_of(env[record[model_field]].browse(record[id_field]).exists())
                    if partner:
                        row_actions[name] = ('person', partner.id)
            if self_named and (partner := record.partner_id):
                for name in PARTNER_NAME_FIELDS:
                    row_actions[name] = ('person', partner.id)
            if tracking:
                self._tracking_actions(record, row_actions)
        self.load_persons(
            pid for acts in actions.values() for act in acts.values() if act[0] == 'person'
            for pid in [act[1]]
        )
        return actions

    def _tracking_actions(self, record, row_actions):
        """Tracked values follow the exposure of the field they track."""
        field = record.field_id
        if not field:
            return
        level = self.level(field.model, field.name) if field.model in self.env else 'allow'
        if field.relation in self.blocked:
            level = 'block'
        if level == 'block' or (level == 'tokenize' and self.external):
            for name in TRACKING_ALL:
                row_actions[name] = ('block',)
        elif level == 'tokenize':
            for name in TRACKING_ALL:
                if 'integer' not in name and 'float' not in name:
                    row_actions[name] = ('tokenize', field.name)
        elif field.ttype == 'many2one' and field.relation in PEOPLE_MODELS:
            for char, integer in TRACKING_VALUES.items():
                if pid := record[integer]:
                    partner = self._partner_of(self._sudo()[field.relation].browse(pid).exists())
                    if partner:
                        row_actions[char] = ('person', partner.id)

    def _nested(self, field, value):
        """Mask a relational value read as a dict or list of dicts (web_read)."""
        if field.comodel_name in self.blocked:
            return False if field.type == 'many2one' else []
        if isinstance(value, dict):
            return self.rows(field.comodel_name, [value])[0]
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            return self.rows(field.comodel_name, value)
        return value

    # -- rows -----------------------------------------------------------
    def rows(self, model_name, rows):
        model_fields = self.env[model_name]._fields
        is_partner = model_name == PARTNER
        people_m2o = {
            name: field.comodel_name for name, field in model_fields.items()
            if field.type == 'many2one' and field.comodel_name in PEOPLE_MODELS
        }
        if self.persons:
            ids = {PARTNER: set(), USERS: set()}
            for row in rows:
                if is_partner:
                    ids[PARTNER].add(row.get('id'))
                for name in people_m2o.keys() & row.keys():
                    if isinstance(row[name], (list, tuple)) and row[name]:
                        ids[people_m2o[name]].add(row[name][0])
            for comodel, comodel_ids in ids.items():
                self.load_labels(comodel, comodel_ids)
        actions = self._row_actions(model_name, rows)
        result = []
        for row in rows:
            row_actions = actions.get(row.get('id'), {})
            masked = {}
            for name, value in row.items():
                if name == 'id':
                    masked[name] = value
                    continue
                level = self.level(model_name, name)
                field = model_fields.get(name)
                action = row_actions.get(name)
                if level == 'block' or (level == 'tokenize' and self.external):
                    if self.blocked_link(model_name, name):
                        masked[name] = False  # R15: the field exists, the link is hidden
                    continue
                if action and action[0] == 'block':
                    continue
                if level == 'tokenize':
                    value = self.emit_field(name, value)
                elif action and action[0] == 'tokenize':
                    value = self.emit_field(action[1], value)
                elif action and action[0] == 'person':
                    if self.is_person(action[1]):
                        value = self.emit('NAME', value)
                elif field is not None and field.relational and isinstance(value, (dict, list)) \
                        and (isinstance(value, dict) or any(isinstance(v, dict) for v in value)):
                    value = self._nested(field, value)
                elif name in people_m2o and value:
                    value = self.mask_label(value, people_m2o[name])
                elif is_partner and name in PARTNER_NAME_FIELDS and self.is_person(row.get('id')):
                    value = self.emit('NAME', value)
                masked[name] = value
            result.append(masked)
        return result

    def pairs(self, model_name, pairs):
        """Mask ``(id, display_name)`` pairs of ``name_search``."""
        rows = self.rows(model_name, [{'id': i, 'display_name': n} for i, n in pairs])
        return [[row['id'], row['display_name']] for row in rows]

    # -- read_group -----------------------------------------------------
    def spec(self, model_name, spec):
        """Resolve a groupby/aggregate spec to ``(level, model, field)`` of its last field.

        ``level`` adds ``'name'`` for any copy of a partner or user name (the
        name itself, a related or computed copy): grouped values carry no id,
        so :meth:`mask_name` tells a person from a company by the name.
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
        if self._name_link(model, field) is not None:
            return 'name', model, field
        return 'allow', model, field

    def mask_name(self, value):
        """Mask a bare person name (no id): ``NAME#`` unless it names only companies or team.

        Fails closed: a name no partner carries, that any person carries, or
        carried by more than ``NAME_LOOKUP_CAP`` partners, is tokenized.
        """
        if not self.persons or _is_empty(value) or isinstance(value, bool):
            return value
        if isinstance(value, (list, tuple)):
            return [self.mask_name(v) for v in value]
        if not isinstance(value, str):
            return value
        if value not in self._names:
            ids = self._sudo()[PARTNER].search([('name', '=', value)], limit=NAME_LOOKUP_CAP + 1).ids
            if not ids or len(ids) > NAME_LOOKUP_CAP:
                # nobody, or too many to check them all: fail closed
                self._names[value] = True
            else:
                self.load_persons(ids)
                self._names[value] = any(self._persons.get(i, True) for i in ids)
        return self.emit('NAME', value) if self._names[value] else value

    def groups(self, model_name, groupby, aggregates, groups, unfold_model=None):
        """Mask grouped results; ``aggregates`` is a list of specs or a ``{key: field}`` map.

        Keys that are neither a groupby, an aggregate nor a known meta key are
        dropped unless numeric (fail closed). ``__records`` / ``__groups`` of
        ``web_read_group`` are masked too.
        """
        if not isinstance(aggregates, dict):
            aggregates = {spec: spec.split(':')[0] for spec in aggregates}
        specs = {spec: self.spec(model_name, spec) for spec in groupby}
        aggs = {
            key: self.spec(model_name, fname)
            for key, fname in aggregates.items() if key != '__count'
        }
        if self.persons:
            for spec, (_level, _model, field) in specs.items():
                if field is not None and field.relational and field.comodel_name in PEOPLE_MODELS:
                    self.load_labels(field.comodel_name, [
                        g[spec][0] for g in groups if isinstance(g.get(spec), (list, tuple))
                    ])
        for group in groups:
            for spec, (level, _model, field) in specs.items():
                if spec not in group:
                    continue
                value = group[spec]
                if level == 'block' or (level == 'tokenize' and self.external):
                    group[spec] = False
                    group.pop('__extra_domain', None)
                    group.pop('__domain', None)
                elif level == 'tokenize':
                    group[spec] = self.emit_field(field.name, value)
                    for key in ('__extra_domain', '__domain'):
                        if not self.tokens or key not in group:
                            continue
                        if '.' in spec.split(':')[0]:
                            group.pop(key)
                        else:
                            group[key] = self._mask_domain(group[key], field.name)
                elif level == 'name':
                    group[spec] = self.mask_name(value)
                    if group[spec] != value:
                        group.pop('__extra_domain', None)
                        group.pop('__domain', None)
                elif field is not None and field.relational and isinstance(value, dict):
                    group[spec] = self._nested(field, value)
                elif field is not None and field.relational and field.comodel_name in PEOPLE_MODELS:
                    group[spec] = self.mask_label(value, field.comodel_name)
            for spec, (level, _model, field) in aggs.items():
                if spec not in group:
                    continue
                value = group[spec]
                if level == 'block' or (level == 'tokenize' and self.external):
                    group.pop(spec)  # even a count or a sum tells about the value
                    continue
                if isinstance(value, numbers.Number) and not isinstance(value, bool):
                    continue  # counts and sums of shown fields carry no personal value
                if field is None:
                    group.pop(spec)
                elif level == 'tokenize':
                    group[spec] = self.emit_field(field.name, value)
                elif level == 'name':
                    group[spec] = self.mask_name(value)
            if '__records' in group:
                group['__records'] = self.rows(unfold_model or model_name, group['__records'] or [])
            if isinstance(group.get('__groups'), dict):
                sub = group['__groups']
                sub['groups'] = self.groups(
                    model_name, groupby[1:], aggregates, sub.get('groups') or [], unfold_model
                )
            if '__count' in group and not (
                isinstance(group['__count'], int) and not isinstance(group['__count'], bool)
            ):
                group.pop('__count')
            if '__fold' in group and not isinstance(group['__fold'], bool):
                group.pop('__fold')
            for key in list(group):
                if key in specs or key in aggs or key in GROUP_META_KEYS or key in ('__records', '__groups'):
                    continue
                value = group[key]
                if not (isinstance(value, numbers.Number) and not isinstance(value, bool)):
                    group.pop(key)  # unknown key with a value: fail closed
        return groups

    def _mask_domain(self, domain, name):
        masked = []
        for leaf in domain:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3 and leaf[0] == name:
                leaf = (leaf[0], leaf[1], self.emit_field(name, leaf[2]))
            masked.append(leaf)
        return masked

