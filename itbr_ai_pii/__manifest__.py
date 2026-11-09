{
    'name': 'IT Brasil Personal Data Masking',
    'summary': 'Neutral core that masks personal data (CPF, CNPJ, e-mail, phone) as HMAC tokens',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'IT Brasil',
    'website': 'https://github.com/itbrasil-odoo/themes',
    'depends': ['base'],
    'data': [
        'security/ir.access.csv',
        'data/ir_config_parameter.xml',
        'data/ir_cron.xml',
        'views/ir_model_fields.xml',
        'views/res_config_settings.xml',
        'data/ir_model_fields.xml',
    ],
    'installable': True,
}
