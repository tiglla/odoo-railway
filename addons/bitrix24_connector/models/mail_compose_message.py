from odoo import fields, models, _
from odoo.exceptions import UserError


class MailComposeMessageBitrix(models.TransientModel):
    _inherit = "mail.compose.message"

    def _action_send_mail_comment(self, res_ids):
        template = self.env.ref(
            "eigr_construction_management.email_template_eigr_client_progress",
            raise_if_not_found=False,
        )
        is_eigr_report = (
            template and self.model == "eigr.construction.project"
            and self.template_id == template
        )
        if is_eigr_report:
            config = self.env["bitrix.config"].sudo().search([("active", "=", True)], limit=1)
            projects = self.env[self.model].browse(res_ids)
            if config and config.client_notification_mode == "bitrix" and projects.filtered("bitrix_deal_id"):
                raise UserError(_("Los avisos de avance de estas obras se envían desde Bitrix24."))
        messages = super()._action_send_mail_comment(res_ids)
        if messages and is_eigr_report:
            projects = self.env[self.model].browse(res_ids)
            notified = projects.filtered(lambda project: any(
                message.model == project._name and message.res_id == project.id
                and project.client_id in message.partner_ids
                for message in messages
            ))
            if notified:
                notified.sudo().write({
                    "bitrix_client_contact_at": fields.Date.context_today(self),
                })
        return messages
