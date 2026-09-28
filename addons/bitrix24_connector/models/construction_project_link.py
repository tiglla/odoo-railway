import hashlib
import json
from uuid import uuid4

from odoo import fields, models, api, _
from odoo.exceptions import UserError


class EigrConstructionProjectBitrixLink(models.Model):
    _inherit = "eigr.construction.project"

    bitrix_deal_id = fields.Char(
        string="ID del negocio Bitrix24",
        index=True,
        copy=False,
        readonly=True,
    )
    bitrix_export_hash = fields.Char(
        string="Última versión enviada a Bitrix24", readonly=True, copy=False
    )
    bitrix_progress_updated_at = fields.Datetime(
        string="Última actualización de avance", readonly=True, copy=False,
    )
    bitrix_client_contact_at = fields.Date(
        string="Último aviso al cliente", readonly=True, copy=False,
    )

    _bitrix_deal_id_unique = models.Constraint(
        "UNIQUE(bitrix_deal_id)",
        "El negocio de Bitrix24 ya tiene una obra vinculada.",
    )

    def write(self, vals):
        previous = {project.id: project.state for project in self} if "state" in vals else {}
        tracked = {"state", "progress_percent", "planned_end_date"}
        if tracked.intersection(vals):
            vals = {**vals, "bitrix_progress_updated_at": fields.Datetime.now()}
        result = super().write(vals)
        if "state" in vals:
            Event = self.env["bitrix.progress.event"].sudo()
            labels = dict(self._fields["state"].selection)
            for project in self.filtered("bitrix_deal_id"):
                if previous[project.id] != project.state:
                    Event.create({
                        "project_id": project.id,
                        "event_key": uuid4().hex,
                        "comment": f"Obra {project.code}: fase cambiada a {labels.get(project.state, project.state)}.",
                    })
        return result

    def action_record_client_contact(self):
        self.check_access("write")
        self.sudo().write({"bitrix_client_contact_at": fields.Date.context_today(self)})
        return True

    def action_prepare_client_report(self):
        config = self.env["bitrix.config"].sudo().search([("active", "=", True)], limit=1)
        if config and config.client_notification_mode == "bitrix" and self.filtered("bitrix_deal_id"):
            raise UserError(_(
                "Los avisos de avance se gestionan desde Bitrix24. "
                "Cambie el canal a Odoo para enviar el informe por correo desde aquí."
            ))
        return super().action_prepare_client_report()

    def _bitrix_progress_payload(self, config):
        self.ensure_one()
        milestones = self.schedule_ids.filtered(
            lambda item: item.is_milestone and item.actual_percent < 100
        ).sorted("end_date")
        next_milestone = milestones[:1]
        delay = max((item.delay_days for item in self.schedule_ids), default=0)
        mapping = {
            "deal_field_project_code": self.code or "",
            "deal_field_project_state": dict(self._fields["state"].selection).get(
                self.state, self.state
            ),
            "deal_field_project_progress": self.progress_percent,
            "deal_field_project_end_date": (
                str(self.planned_end_date) if self.planned_end_date else False
            ),
            "deal_field_next_milestone": next_milestone.name if next_milestone else "",
            "deal_field_milestone_date": (
                str(next_milestone.end_date) if next_milestone else False
            ),
            "deal_field_delay_days": delay,
            "deal_field_client_contact": (
                str(self.bitrix_client_contact_at) if self.bitrix_client_contact_at else False
            ),
        }
        if config.client_notification_mode == "bitrix":
            mapping["deal_field_progress_update"] = (
                self.bitrix_progress_updated_at.isoformat() + "Z"
                if self.bitrix_progress_updated_at else False
            )
        payload = {}
        for setting, value in mapping.items():
            field_code = (config[setting] or "").strip().upper()
            if field_code:
                if not field_code.startswith("UF_CRM_"):
                    raise ValueError(
                        f"El campo Bitrix24 {field_code} debe comenzar con UF_CRM_."
                    )
                payload[field_code] = value
        return payload

    def sync_progress_with_bitrix(self, api, config):
        exported = 0
        errors = []
        projects = self.sudo().search([("bitrix_deal_id", "!=", False)])
        if not projects:
            return exported, errors
        expected_types = {
            "deal_field_project_code": "string",
            "deal_field_project_state": "string",
            "deal_field_project_progress": "double",
            "deal_field_project_end_date": "date",
            "deal_field_next_milestone": "string",
            "deal_field_milestone_date": "date",
            "deal_field_delay_days": "integer",
            "deal_field_progress_update": "datetime",
            "deal_field_client_contact": "date",
        }
        configured = {
            (config[name] or "").strip().upper(): field_type
            for name, field_type in expected_types.items()
            if config[name]
        }
        if configured:
            try:
                available = {
                    item["FIELD_NAME"]: item.get("USER_TYPE_ID")
                    for item in api.get_deal_userfields()
                }
            except Exception as error:
                return exported, [f"No se pudieron verificar los campos de obra: {error}"]
            missing = configured.keys() - available.keys()
            if missing:
                return exported, [
                    f"Campos de obra inexistentes en Bitrix24: {', '.join(sorted(missing))}"
                ]
            invalid_types = [
                code for code, expected in configured.items()
                if available[code] != expected
            ]
            if invalid_types:
                return exported, [
                    f"Campos de obra con tipo incorrecto: {', '.join(sorted(invalid_types))}"
                ]
        for project in projects:
            try:
                payload = project._bitrix_progress_payload(config)
            except ValueError as error:
                errors.append(str(error))
                break
            if not payload:
                continue
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            if project.bitrix_export_hash == digest:
                continue
            success, _result, error = config._push_record(
                project,
                "crm.deal.update",
                payload,
                lambda: api.update_deal(project.bitrix_deal_id, payload),
            )
            if error:
                errors.append(f"Obra {project.code}: {error}")
            elif success:
                project.bitrix_export_hash = digest
                exported += 1
        errors.extend(self.env["bitrix.progress.event"].sudo().search([
            ("posted", "=", False), ("project_id.bitrix_deal_id", "!=", False),
        ]).publish(api, config))
        return exported, errors


class EigrScheduleBitrixUpdate(models.Model):
    _inherit = "eigr.construction.schedule"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("project_id").sudo().write({
            "bitrix_progress_updated_at": fields.Datetime.now(),
        })
        return records

    def write(self, vals):
        projects = self.mapped("project_id")
        result = super().write(vals)
        if {"name", "end_date", "is_milestone", "actual_percent", "completion_date"} & set(vals):
            (projects | self.mapped("project_id")).sudo().write({
                "bitrix_progress_updated_at": fields.Datetime.now(),
            })
        return result

    def unlink(self):
        projects = self.mapped("project_id")
        result = super().unlink()
        projects.sudo().write({
            "bitrix_progress_updated_at": fields.Datetime.now(),
        })
        return result


class EigrValuationBitrixUpdate(models.Model):
    _inherit = "eigr.construction.valuation"

    def write(self, vals):
        to_approve = self.filtered(lambda item: item.state != "approved") if vals.get("state") == "approved" else self.browse()
        result = super().write(vals)
        Event = self.env["bitrix.progress.event"].sudo()
        for valuation in to_approve.filtered(lambda item: item.state == "approved"):
            project = valuation.project_id
            project.sudo().write({"bitrix_progress_updated_at": fields.Datetime.now()})
            if project.bitrix_deal_id:
                Event.create({
                    "project_id": project.id,
                    "event_key": f"valuation-{valuation.id}",
                    "comment": (
                        f"Obra {project.code}: valorización {valuation.code} aprobada "
                        f"con avance de {valuation.actual_progress:.2f}% "
                        f"al {valuation.cutoff_date}."
                    ),
                })
        return result
