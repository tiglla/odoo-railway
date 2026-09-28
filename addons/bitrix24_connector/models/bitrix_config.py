import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..services.bitrix_api import BitrixAPI

_logger = logging.getLogger(__name__)


class BitrixConfig(models.Model):
    _name = "bitrix.config"
    _description = "Configuración Bitrix24"

    name = fields.Char(
        string="Nombre",
        required=True,
        default="Bitrix24",
    )

    webhook_url = fields.Char(
        string="Webhook URL",
        required=True,
        help="URL del webhook entrante de Bitrix24.",
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
    )

    sync_interval = fields.Integer(
        string="Intervalo de sincronización (minutos)",
        default=60,
        help="Cada cuántos minutos se ejecuta la sincronización "
             "automática. Usa 0 para desactivarla.",
    )

    last_sync = fields.Datetime(
        string="Última sincronización",
        readonly=True,
    )

    def action_sync_now(self):

        self.ensure_one()

        try:

            result = self.env[
                "res.partner"
            ].sync_with_bitrix(self)

        except Exception as error:

            raise UserError(
                _("Error sincronizando con Bitrix24: %s")
                % error
            )

        errors = result.get("sync_errors", [])
        message = _(
            "Sync completado. Contactos "
            "N: %(imported)s | A: %(updated)s | "
            "E: %(exported)s | Empresas "
            "N: %(companies_imported)s | "
            "A: %(companies_updated)s | "
            "E: %(companies_exported)s | "
            "Negocios N: %(deals_imported)s | "
            "A: %(deals_updated)s | "
            "E: %(deals_exported)s"
        ) % result
        if errors:
            message += _(" | Fallidos: %s. ") % len(errors)
            message += " | ".join(errors[:3])
            if len(errors) > 3:
                message += _(" | Revise los logs para ver los demás.")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bitrix24"),
                "message": message,
                "type": "warning" if errors else "success",
                "sticky": bool(errors),
            },
        }

    @api.model
    def _cron_sync(self):

        config = self.search(
            [("active", "=", True)],
            limit=1,
        )

        if not config or not config.webhook_url:
            return

        if not config.sync_interval:
            return

        if config.last_sync:

            elapsed = (
                fields.Datetime.now() - config.last_sync
            ).total_seconds() / 60

            if elapsed < config.sync_interval:
                return

        try:

            config.env[
                "res.partner"
            ].sync_with_bitrix(config)

        except Exception as error:

            _logger.error(
                "Bitrix24: fallo en la sincronización "
                "automática: %s",
                error,
            )

    def action_test_connection(self):

        self.ensure_one()

        api = BitrixAPI(self.webhook_url)

        try:
            profile = api.test_connection()

        except Exception as error:
            raise UserError(
                _("Error conectando con Bitrix24: %s") % error
            )

        result = profile.get("result") or {}

        user_name = " ".join(
            part
            for part in [
                result.get("NAME"),
                result.get("LAST_NAME"),
            ]
            if part
        ) or result.get("ID", "")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bitrix24"),
                "message": _(
                    "Conexión correcta. Usuario: %s"
                ) % user_name,
                "type": "success",
                "sticky": False,
            },
        }

    def action_import_contacts(self):

        self.ensure_one()

        return self.env[
            "res.partner"
        ].import_bitrix_contacts()
