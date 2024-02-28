{
    'name': 'IT Brasil Backend Theme',
    'summary': 'Odoo Community Backend Theme',
    'version': '16.0.2.0.1',
    'category': 'Themes/Backend',
    'license': 'LGPL-3',
    'author': 'IT Brasil',
    'website': 'https://www.itbrasil.com.br',
    'depends': [
        'base_setup',
        'web_editor',
        'mail',
    ],
    'excludes': [
        'web_enterprise',
    ],
    'data': [
        'templates/webclient.xml',
        'views/res_config_settings.xml',
        'views/res_users.xml',
        'views/web_login.xml'
    ],
    'assets': {
        'web._assets_primary_variables': [
            (
                'after',
                'web/static/src/scss/primary_variables.scss',
                'itbr_web_theme/static/src/colors.scss'
            ),
        ],
        'web._assets_backend_helpers': [
            'itbr_web_theme/static/src/variables.scss',
            'itbr_web_theme/static/src/mixins.scss',
        ],
        'web.assets_backend': [
            'itbr_web_theme/static/src/core/**/*.xml',
            'itbr_web_theme/static/src/core/**/*.scss',
            'itbr_web_theme/static/src/core/**/*.js',
            'itbr_web_theme/static/src/webclient/**/*.xml',
            'itbr_web_theme/static/src/webclient/**/*.scss',
            'itbr_web_theme/static/src/webclient/*.js',
            'itbr_web_theme/static/src/webclient/**/*.js',
            'itbr_web_theme/static/src/views/**/*.scss',
        ],
    },
    'images': [
        'static/description/banner.png',
        'static/description/theme_screenshot.png'
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'uninstall_hook': '_uninstall_cleanup',
}
