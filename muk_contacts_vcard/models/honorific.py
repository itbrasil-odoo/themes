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
        string='Abbreviation', 
        required=True, 
        translate=True
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
