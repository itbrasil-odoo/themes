{
    'name': 'ServIAm Personal Data',
    'summary': 'Keeps personal data out of the AI provider in ServIAm chats',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'IT Brasil',
    'website': 'https://github.com/itbrasil-odoo/themes',
    'depends': ['muk_ai'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/res_config_settings.xml',
    ],
    'installable': True,
}
