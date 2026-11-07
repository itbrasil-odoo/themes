from odoo import api, fields, models, tools
from odoo.exceptions import AccessError

EXPOSURE = [
    ('allow', 'Allowed'),
    ('tokenize', 'Tokenized'),
    ('block', 'Blocked'),
]

BLOCK_NAMES = frozenset({
    'password', 'acc_number', 'iban', 'wage', 'salary',
    'ssnid', 'passport_id', 'identification_id', 'permit_no', 'visa_no',
})
BLOCK_FIRST_PARTS = frozenset({'bank', 'private'})

# only values that can carry text or a date are worth tokenizing
TOKENIZE_TYPES = frozenset({'char', 'text', 'html', 'date', 'datetime'})
TOKENIZE_NAMES = frozenset({
    'vat', 'cnpj_cpf', 'birthday', 'contact_name', 'partner_name',
    'invoice_partner_display_name',
})
TOKENIZE_SUFFIXES = ('_partner_name',)
# any name part starting with one of these (cpf -> cpf, cpf_cnpj, ...)
TOKENIZE_PART_PREFIXES = ('cpf', 'cnpj', 'email', 'phone', 'mobile', 'street', 'zip', 'birth')
# any name part equal to one of these (pt-BR synonyms)
TOKENIZE_PARTS = frozenset({'telefone', 'celular', 'cep', 'nascimento', 'endereco', 'rua'})


def classify_field(model, name, ttype):
    """Return 'allow', 'tokenize' or 'block' for one field (first match wins).

    Keywords are matched against the parts of the name (split on '_', after
    dropping the x_ / x_studio_ prefix of custom fields), so x_responsavel_cpf
    is caught as well as cpf_responsavel.
    """
    name = (name or '').lower()
    for prefix in ('x_studio_', 'x_'):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    parts = name.split('_')
    if (
        name in BLOCK_NAMES
        or parts[-1].endswith('token')
        or parts[0] in BLOCK_FIRST_PARTS
        or (model == 'hr.employee' and ttype == 'binary')
    ):
        return 'block'
    if ttype in TOKENIZE_TYPES and (
        name in TOKENIZE_NAMES
        or name.endswith(TOKENIZE_SUFFIXES)
        or any(part.startswith(TOKENIZE_PART_PREFIXES) or part in TOKENIZE_PARTS for part in parts)
        or (model == 'res.users' and name == 'login')
    ):
        return 'tokenize'
    return 'allow'


class IrModelFields(models.Model):
    _inherit = 'ir.model.fields'

    ai_exposure_auto = fields.Selection(
        EXPOSURE,
        string='Automatic AI Exposure',
        compute='_compute_ai_exposure_auto',
        store=True,
        index=True,
    )
    ai_exposure_override = fields.Selection(
        EXPOSURE,
        string='AI Exposure Override',
        help='Exception to the automatic classification. Leave empty to follow it.',
    )
    ai_exposure = fields.Selection(
        EXPOSURE,
        string='AI Exposure',
        compute='_compute_ai_exposure',
        store=True,
        index=True,
    )

    @api.depends('name', 'ttype', 'model')
    def _compute_ai_exposure_auto(self):
        for field in self:
            field.ai_exposure_auto = classify_field(field.model, field.name, field.ttype)

    @api.depends('ai_exposure_auto', 'ai_exposure_override')
    def _compute_ai_exposure(self):
        for field in self:
            field.ai_exposure = field.ai_exposure_override or field.ai_exposure_auto

    @tools.ormcache('model_name')
    def _ai_exposure_map(self, model_name):
        """Field name -> 'allow' | 'tokenize' | 'block' for one model."""
        self.flush_model(['model', 'name', 'ai_exposure'])
        self.env.cr.execute(
            'SELECT name, ai_exposure, ttype FROM ir_model_fields WHERE model = %s',
            [model_name],
        )
        # fail closed: a row without a stored value is classified on the spot
        return {
            name: exposure or classify_field(model_name, name, ttype)
            for name, exposure, ttype in self.env.cr.fetchall()
        }

    def write(self, vals):
        # ir.model.fields.write refuses to touch base fields; the exposure
        # override is metadata of ours and must stay editable on any field.
        own = {k: v for k, v in vals.items() if k == 'ai_exposure_override'}
        rest = {k: v for k, v in vals.items() if k not in own}
        result = True
        if rest:
            result = super().write(rest)
        if own:
            if not (self.env.su or self.env.user._is_system()):
                raise AccessError(self.env._('Only administrators can change the AI exposure of a field.'))
            result = models.BaseModel.write(self, own)
            self.env.registry.clear_cache()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env.registry.clear_cache()
        return records
