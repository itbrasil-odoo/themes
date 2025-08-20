import json

from lxml import etree

from odoo import _, api, fields, models


class MailMessage(models.Model):
    
    _inherit = 'mail.message'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if (
            self.env.user.has_group('base.group_erp_manager') and
            view == self.env.ref('muk_mail_route.view_mail_message_failed_list')
        ):
            models = self.env['ir.model.access']._get_allowed_models()
            configurations = self.env['muk_mail_route.configuration'].search(
                [('model_id.model', 'in', list(models))], order='sequence DESC'
            )
            for node in arch.xpath(".//button[@name='action_route_message']"):
                for configuration in configurations:
                    button = etree.Element("button", {
                        'class': 'btn-secondary',
                        'string': configuration.name,
                        'name': 'action_route_message',
                        'type': 'object',
                        'groups': 'base.group_erp_manager',
                        'context': json.dumps({
                            'default_configuration_id': configuration.id,
                        }),
                    })
                    node.addnext(button)
        return arch, view

    # ----------------------------------------------------------
    # Action
    # ----------------------------------------------------------
    
    def action_route_message(self):
        return {
            'name': _('Route Message'),
            'res_model': 'muk_mail_route.router',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_message_ids': [fields.Command.set(self.ids)],
            },
        }
