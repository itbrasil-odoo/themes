from odoo import api, models, fields, _
from odoo.exceptions import UserError


class Honorific(models.Model):
    
    _name = 'muk_contacts_vcard.honorific'
    _description = "Honorific"
    _order = 'sequence ASC'
    
    #----------------------------------------------------------
    # Fields
    #----------------------------------------------------------
    
    name = fields.Char(
        string='Title', 
        required=True, 
        translate=True
    )

    shortcut = fields.Char(
        compute='_compute_shortcut',
        string='Abbreviation', 
        required=True, 
        translate=True,
        precompute=True,
        readonly=False,
        store=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )
    
    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )
    
    position = fields.Selection(
        selection=[
            ('preceding', 'Preceding'),
            ('following', 'Following'),
        ],
        required=True, 
        default='preceding',
    )

    @api.depends('name')
    def _compute_shortcut(self):
        for record in self.filtered(
            lambda r: not r.shortcut
        ):
            record.shortcut = record.name
