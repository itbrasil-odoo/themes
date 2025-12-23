# -*- coding: utf-8 -*-

{
    'name': 'Login Page Cleanup | Remove Powered by Odoo, Superuser, and Database Links',
    'summary': 'Removes "Powered by Odoo", Superuser button, and Databases link from '
               'all authentication pages (Login, Signup, Reset Password).',
    'description': """
        This module cleans up Odoo authentication pages by removing unnecessary 
        links and branding elements for a more professional and white-labeled interface.
        Hide All over Login Page | Sign Up Page | Reset Password Page
        
        Key Features:
        - Removes "Powered by Odoo" footer text and link.
        - Hides the "Manage Databases" option.
        - Disables Superuser/Redirect button.
        - Applies changes to Login, Signup, and Reset Password pages.    
    """,
    'author': 'CodeSphere Tech',
    'website': 'https://www.codespheretech.in/',
    'category': 'Web',
    'version': '19.0.1.0.0',
    'sequence': 0,
    'currency': 'USD',
    'price': '0.00',
    'depends': ['web', 'auth_signup'],
    'data': [
        'views/webclient_templates.xml',
    ],
    'images': ['static/description/Banner.png'],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
