import re
import uuid
import base64

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    theme_favicon = fields.Binary(
        related='company_id.favicon',
        readonly=False
    )

    theme_background_image = fields.Binary(
        related='company_id.background_image',
        readonly=False
    )

    theme_color_brand = fields.Char(
        string='Theme Brand Color'
    )

    theme_color_primary = fields.Char(
        string='Theme Primary Color'
    )

    theme_color_menu = fields.Char(
        string='Theme Menu Color'
    )

    theme_color_appbar_color = fields.Char(
        string='Theme AppBar Color'
    )

    theme_color_appbar_background = fields.Char(
        string='Theme AppBar Background'
    )

    web_window_title = fields.Char(
        string='Window Title',
    )

    # ----------------------------------------------------------
    # Action
    # ----------------------------------------------------------

    def action_reset_theme_assets(self):
        self.env['web_editor.assets'].reset_asset(
            '/itbr_web_theme/static/src/colors.scss', 'web._assets_primary_variables',
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def set_values(self):
        res = super(ResConfigSettings, self).set_values()
        ir_config = self.env['ir.config_parameter'].sudo()
        ir_config.set_param('web.base.title', self.web_window_title or "")
        variables = [
            'o-brand-odoo',
            'o-brand-primary',
            'mk-menu-color',
            'mk-appbar-color',
            'mk-appbar-background',
        ]
        colors = self.env['web_editor.assets'].get_theme_variables_values(
            '/itbr_web_theme/static/src/colors.scss', 'web._assets_primary_variables', variables
        )
        colors_changed = []
        colors_changed.append(self.theme_color_brand != colors['o-brand-odoo'])
        colors_changed.append(self.theme_color_primary != colors['o-brand-primary'])
        colors_changed.append(self.theme_color_menu != colors['mk-menu-color'])
        colors_changed.append(self.theme_color_appbar_color
                              != colors['mk-appbar-color'])
        colors_changed.append(self.theme_color_appbar_background
                              != colors['mk-appbar-background'])
        if(any(colors_changed)):
            variables = [
                {'name': 'o-brand-odoo', 'value': self.theme_color_brand or "#202459"},
                {'name': 'o-brand-primary', 'value': self.theme_color_primary or "#3b4ba7"},
                {'name': 'mk-menu-color', 'value': self.theme_color_menu or "#f8f9fa"},
                {'name': 'mk-appbar-color', 'value': self.theme_color_appbar_color or "#dee2e6"},
                {'name': 'mk-appbar-background',
                    'value': self.theme_color_appbar_background or "#000000"},
            ]
            self.env['web_editor.assets'].replace_theme_variables_values(
                '/itbr_web_theme/static/src/colors.scss', 'web._assets_primary_variables', variables
            )
        return res

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        ir_config = self.env['ir.config_parameter'].sudo()
        web_window_title = ir_config.get_param('web.base.title', default='IT Solution')
        variables = [
            'o-brand-odoo',
            'o-brand-primary',
            'mk-menu-color',
            'mk-appbar-color',
            'mk-appbar-background',
        ]
        colors = self.env['web_editor.assets'].get_theme_variables_values(
            '/itbr_web_theme/static/src/colors.scss', 'web._assets_primary_variables', variables
        )
        res.update({
            'theme_color_brand': colors['o-brand-odoo'],
            'theme_color_primary': colors['o-brand-primary'],
            'theme_color_menu': colors['mk-menu-color'],
            'theme_color_appbar_color': colors['mk-appbar-color'],
            'theme_color_appbar_background': colors['mk-appbar-background'],
            'web_window_title':web_window_title
        })
        return res
