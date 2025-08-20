from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    #----------------------------------------------------------
    # Fields
    #----------------------------------------------------------

    active_product_default_code_automation = fields.Boolean(
        string="Active Product Internal Reference Automation",
    )

    active_product_barcode_automation = fields.Boolean(
        string="Active Product Barcode Automation",
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_product_sequence_active(self, xmlid):
        sequence = self.env.ref(xmlid, False)
        return sequence.active if sequence else False

    @api.model
    def _set_product_sequence_active(self, xmlid, active):
        sequence = self.env.ref(xmlid, False)
        if not sequence:
            raise UserError(_(
                "The sequence couldn't be found."
            ))
        sequence.write({'active': active})

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_values(self):
        res = super().get_values()
        res.update({
            'active_product_default_code_automation': self._get_product_sequence_active(
                'muk_product.seq_product_reference'
            ),
            'active_product_barcode_automation': self._get_product_sequence_active(
                'muk_product.seq_product_barcode'
            ),
        })
        return res

    def set_values(self):
        res = super().set_values()
        self._set_product_sequence_active(
            'muk_product.seq_product_reference', 
            self.active_product_default_code_automation
        )
        self._set_product_sequence_active(
            'muk_product.seq_product_barcode', 
            self.active_product_barcode_automation
        )
        return res
