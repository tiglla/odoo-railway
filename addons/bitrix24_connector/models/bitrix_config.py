import logging
import json
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError

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

    contacts_cursor = fields.Datetime(string="Contactos leídos hasta", readonly=True)
    companies_cursor = fields.Datetime(string="Empresas leídas hasta", readonly=True)
    deals_cursor = fields.Datetime(string="Negocios leídos hasta", readonly=True)

    deal_field_project_code = fields.Char(string="Campo Bitrix: código de obra")
    deal_field_project_state = fields.Char(string="Campo Bitrix: estado de obra")
    deal_field_project_progress = fields.Char(string="Campo Bitrix: avance físico")
    deal_field_project_end_date = fields.Char(string="Campo Bitrix: fecha prevista")
    deal_field_next_milestone = fields.Char(string="Campo Bitrix: próximo hito")
    deal_field_milestone_date = fields.Char(string="Campo Bitrix: fecha del hito")
    deal_field_delay_days = fields.Char(string="Campo Bitrix: días de atraso")
    deal_field_progress_update = fields.Char(string="Campo Bitrix: última actualización")
    deal_field_client_contact = fields.Char(string="Campo Bitrix: último aviso al cliente")
    event_member_id = fields.Char(string="Member ID del portal Bitrix24", groups="base.group_system")
    event_application_token = fields.Char(
        string="Token de eventos salientes", groups="base.group_system", copy=False,
    )
    client_notification_mode = fields.Selection([
        ("odoo", "Correo desde Odoo"),
        ("bitrix", "Automatización en Bitrix24"),
    ], default="odoo", required=True, string="Avisos de avance al cliente")

    user_mapping_ids = fields.One2many(
        "bitrix.user.mapping", "config_id", string="Vendedores y responsables"
    )

    project_responsible_id = fields.Many2one(
        "res.users",
        string="Responsable de nuevas obras",
        default=lambda self: self.env.ref("base.user_admin"),
        help="Usuario asignado a las obras creadas al ganar un negocio en Bitrix24.",
    )

    @staticmethod
    def _pull_filter(cursor):
        if not cursor:
            return None
        start = cursor - timedelta(minutes=2)
        return {"filter": {">=DATE_MODIFY": start.strftime("%Y-%m-%dT%H:%M:%SZ")}}

    def _originator_id(self):
        return f"ODOO_EIGR_{self.env.cr.dbname}"

    def _due_retry_ids(self, model, operation):
        self.ensure_one()
        logs = self.env["bitrix.sync.log"].sudo().search([
            ("config_id", "=", self.id),
            ("resource_model", "=", model),
            ("operation", "ilike", operation),
            ("status", "=", "failed"),
            ("next_retry", "<=", fields.Datetime.now()),
        ])
        return logs.mapped("resource_id")

    def _push_record(self, record, operation, payload, send):
        """Log every attempt and leave failed records eligible for a later retry."""
        self.ensure_one()
        Log = self.env["bitrix.sync.log"].sudo()
        pending = Log.search([
            ("config_id", "=", self.id),
            ("resource_model", "=", record._name),
            ("resource_id", "=", record.id),
            ("operation", "=", operation),
            ("status", "=", "failed"),
        ], order="id desc", limit=1)
        now = fields.Datetime.now()
        if pending and pending.next_retry and pending.next_retry > now:
            return False, None, None

        attempts = (pending.attempts + 1) if pending else 1
        values = {
            "config_id": self.id,
            "run_datetime": now,
            "direction": "push",
            "resource_model": record._name,
            "resource_id": record.id,
            "operation": operation,
            "payload_json": json.dumps(payload, ensure_ascii=False, default=str),
            "attempts": attempts,
        }
        if pending:
            pending.write({"status": "retried"})
        try:
            result = send()
            if not result:
                raise ValueError("Bitrix24 no confirmó la operación.")
        except Exception as error:
            minutes = min(5 * 2 ** min(attempts - 1, 8), 1440)
            Log.create(dict(
                values,
                status="failed",
                failed=1,
                error_log=str(error),
                next_retry=now + timedelta(minutes=minutes),
            ))
            return False, None, str(error)

        Log.search([
            ("config_id", "=", self.id),
            ("resource_model", "=", record._name),
            ("resource_id", "=", record.id),
            ("operation", "ilike", operation.rsplit(".", 1)[0]),
            ("status", "=", "failed"),
        ]).write({"status": "retried"})
        Log.create(dict(values, status="success", exported=1))
        return True, result, None

    def action_setup_project_fields(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Solo un administrador puede crear campos en Bitrix24."))
        api = BitrixAPI(self.webhook_url)
        definitions = [
            ("deal_field_project_code", "EIGR_OBRA_CODIGO", "string", "Código de obra EIGR"),
            ("deal_field_project_state", "EIGR_OBRA_ESTADO", "string", "Estado de obra EIGR"),
            ("deal_field_project_progress", "EIGR_OBRA_AVANCE", "double", "Avance físico EIGR (%)"),
            ("deal_field_project_end_date", "EIGR_OBRA_FIN", "date", "Fin previsto de obra EIGR"),
            ("deal_field_next_milestone", "EIGR_PROXIMO_HITO", "string", "Próximo hito EIGR"),
            ("deal_field_milestone_date", "EIGR_FECHA_HITO", "date", "Fecha del próximo hito EIGR"),
            ("deal_field_delay_days", "EIGR_DIAS_ATRASO", "integer", "Días de atraso EIGR"),
            ("deal_field_progress_update", "EIGR_ACTUALIZACION", "datetime", "Última actualización EIGR"),
            ("deal_field_client_contact", "EIGR_AVISO_CLIENTE", "date", "Último aviso al cliente EIGR"),
        ]
        try:
            existing = {
                item["FIELD_NAME"]: item
                for item in api.get_deal_userfields()
            }
            values = {}
            for setting, code, field_type, label in definitions:
                full_code = f"UF_CRM_{code}"
                field = existing.get(full_code)
                if field and field.get("USER_TYPE_ID") != field_type:
                    raise ValueError(
                        f"{full_code} ya existe con un tipo distinto de {field_type}."
                    )
                if not field:
                    created_id = api.create_deal_userfield({
                        "FIELD_NAME": code,
                        "USER_TYPE_ID": field_type,
                        "LABEL": label,
                    })
                    if not created_id:
                        raise ValueError(f"Bitrix24 no confirmó la creación de {full_code}.")
                values[setting] = full_code
            self.write(values)
        except Exception as error:
            raise UserError(_("No se pudieron preparar los campos en Bitrix24: %s") % error)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bitrix24"),
                "message": _("Los nueve campos de avance de obra están configurados."),
                "type": "success",
            },
        }

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
        pending_count = self.env["bitrix.sync.log"].sudo().search_count([
            ("config_id", "=", self.id), ("status", "=", "failed")
        ])
        message = _(
            "Sync completado. Contactos "
            "N: %(imported)s | A: %(updated)s | "
            "E: %(exported)s | Empresas "
            "N: %(companies_imported)s | "
            "A: %(companies_updated)s | "
            "E: %(companies_exported)s | "
            "Negocios N: %(deals_imported)s | "
            "A: %(deals_updated)s | "
            "E: %(deals_exported)s | Obras creadas: %(projects_created)s "
            "| Avances enviados: %(projects_exported)s"
        ) % result
        if errors:
            message += _(" | Fallidos: %s. ") % len(errors)
            message += " | ".join(errors[:3])
            if len(errors) > 3:
                message += _(" | Revise los logs para ver los demás.")
        if pending_count:
            message += _(" | Reintentos pendientes: %s.") % pending_count

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bitrix24"),
                "message": message,
                "type": "warning" if (errors or pending_count) else "success",
                "sticky": bool(errors or pending_count),
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

            self.env["bitrix.sync.log"].discard_missing_retries(config)
            due_retry = self.env["bitrix.sync.log"].sudo().search_count([
                ("config_id", "=", config.id),
                ("status", "=", "failed"),
                ("next_retry", "<=", fields.Datetime.now()),
            ])
            if elapsed < config.sync_interval and not due_retry:
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
