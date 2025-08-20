from . import models


def _setup_module(env):
    records = env['res.partner'].search([
        ('firstname', '=', False), 
        ('lastname', '=', False)
    ])
    records._inverse_name()
