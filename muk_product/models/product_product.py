from functools import reduce

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    
    _inherit = 'product.product'

    #----------------------------------------------------------
    # Override Fields
    #----------------------------------------------------------
    
    default_code = fields.Char(
        tracking=True,
        copy=False,
    )
    
    barcode = fields.Char(
        tracking=True,
        copy=False,
    )

    # ----------------------------------------------------------
    # Index
    # ----------------------------------------------------------
    
    _unique_default_code = models.UniqueIndex(
        "(default_code) WHERE default_code IS NOT NULL",
        "Another entry with the same default code already exists.",
    )

    _unique_barcode = models.UniqueIndex(
        "(barcode) WHERE barcode IS NOT NULL",
        "Another entry with the same barcode already exists.",
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_next_default_code(self):
        return self.env['ir.sequence'].next_by_code(
            'product.product.default_code'
        )

    @api.model
    def _get_next_barcode(self):
        code = self.env['ir.sequence'].next_by_code(
            'product.product.barcode'
        )
        if code:
            evensum = reduce(lambda x, y: int(x) + int(y), code[-2::-2])
            oddsum = reduce(lambda x, y: int(x) + int(y), code[-1::-2])
            checksum = (10 - ((evensum + oddsum * 3) % 10)) % 10
            return f'{code}{checksum}'
        return code

    #----------------------------------------------------------
    # ORM
    #----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('default_code', False):
                vals['default_code'] = self._get_next_default_code()
            if not vals.get('barcode', False):
                vals['barcode'] = self._get_next_barcode()
        return super().create(vals_list)
