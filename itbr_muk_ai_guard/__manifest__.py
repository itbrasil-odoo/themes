{
    'name': 'ServIAm Guard',
    'summary': 'Approval on every AI write, admin-only approval switch, no web access, API keys kept off the database',
    'version': '19.0.1.1.0',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'IT Brasil',
    'website': 'https://github.com/itbrasil-odoo/themes',
    'depends': ['muk_ai'],
    'data': [
        'data/ir_config_parameter.xml',
        'views/res_config_settings.xml',
        'views/muk_ai_provider.xml',
    ],
    'installable': True,
}
