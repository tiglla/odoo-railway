import hashlib
import json

from odoo import fields, models


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

    _bitrix_deal_id_unique = models.Constraint(
        "UNIQUE(bitrix_deal_id)",
        "El negocio de Bitrix24 ya tiene una obra vinculada.",
    )

    def _bitrix_progress_payload(self, config):
        self.ensure_one()
        mapping = {
            "deal_field_project_code": self.code or "",
            "deal_field_project_state": dict(self._fields["state"].selection).get(
                self.state, self.state
            ),
            "deal_field_project_progress": self.progress_percent,
            "deal_field_project_end_date": (
                str(self.planned_end_date) if self.planned_end_date else False
            ),
        }
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
        }
        configured = {
            (config[name] or "").strip().upper(): field_type
            for name, field_type in expected_types.items() if config[name]
        }
        if not configured:
            return exported, errors
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
                break
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
        return exported, errors
