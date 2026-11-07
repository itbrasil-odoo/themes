from odoo import api, fields, models, tools

EXPOSURE = [
    ('allow', 'Allowed'),
    ('tokenize', 'Tokenized'),
    ('block', 'Blocked'),
]

BLOCK_NAMES = frozenset({
    'password', 'token', 'acc_number', 'iban', 'wage', 'salary',
    'ssnid', 'passport_id', 'identification_id', 'permit_no', 'visa_no',
})
BLOCK_SUFFIXES = ('_token',)
BLOCK_PREFIXES = ('bank_', 'private_')

TOKENIZE_NAMES = frozenset({
    'vat', 'cnpj_cpf', 'birthday', 'contact_name', 'partner_name',
    'invoice_partner_display_name',
})
TOKENIZE_SUFFIXES = ('_partner_name',)
TOKENIZE_PREFIXES = ('cpf', 'cnpj', 'email', 'phone', 'mobile', 'street', 'zip', 'birth')


def classify_field(model, name, ttype):
    """Return 'allow', 'tokenize' or 'block' for one field (first match wins)."""
    name = (name or '').lower()
    # custom fields carry an x_ (or x_studio_) prefix that hides the real name
    for prefix in ('x_studio_', 'x_'):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    if (
        name in BLOCK_NAMES
        or name.endswith(BLOCK_SUFFIXES)
        or name.startswith(BLOCK_PREFIXES)
        or (model == 'hr.employee' and ttype == 'binary')
    ):
        return 'block'
    if (
        name in TOKENIZE_NAMES
        or name.endswith(TOKENIZE_SUFFIXES)
        or name.startswith(TOKENIZE_PREFIXES)
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
            'SELECT name, ai_exposure FROM ir_model_fields WHERE model = %s',
            [model_name],
        )
        return {name: exposure or 'allow' for name, exposure in self.env.cr.fetchall()}

    def write(self, vals):
        # ir.model.fields.write refuses to touch base fields; the exposure
        # override is metadata of ours and must stay editable on any field.
        own = {k: v for k, v in vals.items() if k == 'ai_exposure_override'}
        rest = {k: v for k, v in vals.items() if k not in own}
        result = True
        if rest:
            result = super().write(rest)
        if own:
            result = models.BaseModel.write(self, own)
            self.env.registry.clear_cache()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env.registry.clear_cache()
        return records
