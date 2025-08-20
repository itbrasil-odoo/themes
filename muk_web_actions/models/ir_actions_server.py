
from odoo import api, fields, models, tools


class IrActionsServer(models.Model):

    _inherit = 'ir.actions.server'

    #----------------------------------------------------------
    # Fields
    #----------------------------------------------------------

    execute_in_batch = fields.Boolean(
        string="Execute in Batch",
        default=False,
        help="""
            If this flag is active the actions are executed in batch. 
            Note that such actions should not set the action variable.
        """
    )

    execution_batch_size = fields.Integer(
        string="Exectution Batch Size",
        default=100,
    )

    #----------------------------------------------------------
    # ORM
    #----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        self.env.registry.clear_cache()
        return res

    def write(self, vals):
        res = super().write(vals)
        self.env.registry.clear_cache()
        return res
