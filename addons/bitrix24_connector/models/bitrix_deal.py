import logging

from odoo import models, fields, api, _

from odoo.exceptions import UserError

from ..services.bitrix_api import BitrixAPI

_logger = logging.getLogger(__name__)

class BitrixDeal(models.Model):
    _name = "bitrix.deal"
    _description = "Negocio Bitrix24"
    _order = "date_modify desc"

    name = fields.Char(string="Título", required=True)

    bitrix_deal_id = fields.Char(
        string="Bitrix24 Deal ID",
        index=True,
        copy=False,
    )

    stage_id = fields.Char(string="Fase (Stage ID)")
    stage_semantic_id = fields.Selection(
        [("P", "En curso"), ("S", "Ganado"), ("F", "Perdido")],
        string="Resultado de la fase",
        readonly=True,
    )
    category_id = fields.Char(string="Categoría (Category ID)")
    opportunity = fields.Float(string="Importe")
    currency_code = fields.Char(string="Moneda Bitrix24", readonly=True)
    assigned_by_id = fields.Char(string="Vendedor Bitrix24", readonly=True)

    partner_id = fields.Many2one("res.partner", string="Contacto")
    company_id = fields.Many2one("res.partner", string="Empresa")
    project_id = fields.Many2one(
        "eigr.construction.project",
        string="Obra creada",
        readonly=True,
        copy=False,
    )

    date_modify = fields.Datetime(string="Última modificación")
    bitrix_last_sync = fields.Datetime(
        string="Última sincronización", readonly=True
    )

    _bitrix_deal_id_unique = models.Constraint(
        "unique(bitrix_deal_id)",
        "El ID del negocio de Bitrix24 debe ser único.",
    )

    def _get_bitrix_config(self):
        config = self.env["bitrix.config"].search(
            [("active", "=", True)], limit=1
        )
        if not config:
            raise UserError(
                _("No existe una configuración activa de Bitrix24.")
            )
        return config

    def _find_partner(self, bitrix_entity, bitrix_id):
        if not bitrix_id:
            return False
        return self.env["res.partner"].search(
            [(bitrix_entity, "=", str(bitrix_id))], limit=1
        )

    @api.model
    def _deal_to_odoo_values(self, deal):
        contact_id = deal.get("CONTACT_ID") or deal.get("CONTACT_IDS", [])
        if isinstance(contact_id, list):
            contact_id = contact_id[0] if contact_id else False

        company_id = deal.get("COMPANY_ID") or deal.get("COMPANY_IDS", [])
        if isinstance(company_id, list):
            company_id = company_id[0] if company_id else False

        return {
            "name": deal.get("TITLE") or "Bitrix Deal",
            "stage_id": deal.get("STAGE_ID"),
            "stage_semantic_id": deal.get("STAGE_SEMANTIC_ID") or False,
            "category_id": deal.get("CATEGORY_ID"),
            "opportunity": deal.get("OPPORTUNITY") or 0.0,
            "currency_code": deal.get("CURRENCY_ID") or False,
            "assigned_by_id": str(deal.get("ASSIGNED_BY_ID") or "") or False,
            "partner_id": self._find_partner(
                "bitrix_contact_id", contact_id
            ).id or False,
            "company_id": self._find_partner(
                "bitrix_company_id", company_id
            ).id or False,
            "date_modify": self.env["res.partner"]._parse_bitrix_date(
                deal.get("DATE_MODIFY")
            ),
        }

    def _ensure_won_projects(self, config):
        Project = self.env["eigr.construction.project"].sudo()
        default_responsible = config.project_responsible_id or self.env.ref(
            "base.user_admin"
        )
        created = 0
        errors = []

        won_deals = self.search([
            ("stage_semantic_id", "=", "S"),
            ("bitrix_deal_id", "!=", False),
            ("project_id", "=", False),
        ])
        for deal in won_deals:
            mapping = config.sudo().user_mapping_ids.filtered(
                lambda item: item.bitrix_user_id == deal.assigned_by_id
            )[:1]
            responsible = mapping.user_id if mapping else default_responsible
            project = Project.with_context(active_test=False).search([
                ("bitrix_deal_id", "=", deal.bitrix_deal_id),
            ], limit=1)
            if project:
                deal.project_id = project.id
                continue

            client = deal.company_id or deal.partner_id
            if not client:
                message = (
                    f"Negocio Bitrix24 {deal.bitrix_deal_id} ({deal.name}): "
                    "no tiene contacto ni empresa vinculados en Odoo; "
                    "no se creó la obra."
                )
                _logger.warning("%s", message)
                errors.append(message)
                continue

            odoo_currency = self.env.company.currency_id.name
            if (
                deal.currency_code
                and deal.currency_code.upper() != odoo_currency.upper()
            ):
                message = (
                    f"Negocio Bitrix24 {deal.bitrix_deal_id} ({deal.name}): "
                    f"moneda {deal.currency_code} distinta de {odoo_currency}; "
                    "no se creó la obra para evitar un monto incorrecto."
                )
                _logger.warning("%s", message)
                errors.append(message)
                continue

            try:
                with self.env.cr.savepoint():
                    project = Project.create({
                        "name": deal.name,
                        "client_id": client.id,
                        "contract_amount": deal.opportunity,
                        "bitrix_deal_id": deal.bitrix_deal_id,
                        "responsible_id": responsible.id,
                    })
                    deal.project_id = project.id
            except Exception as error:
                project = Project.with_context(active_test=False).search([
                    ("bitrix_deal_id", "=", deal.bitrix_deal_id),
                ], limit=1)
                if project:
                    deal.project_id = project.id
                    continue
                message = (
                    f"Negocio Bitrix24 {deal.bitrix_deal_id} ({deal.name}): "
                    f"no se pudo crear la obra: {error}"
                )
                _logger.exception("%s", message)
                errors.append(message)
                continue
            created += 1

        return created, errors

    def action_open_project(self):
        self.ensure_one()
        if not self.project_id:
            raise UserError(_("Este negocio aún no tiene una obra vinculada."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Obra"),
            "res_model": "eigr.construction.project",
            "view_mode": "form",
            "res_id": self.project_id.id,
        }

    def sync_deals_with_bitrix(self, api, quiet=True, config=None):
        imported = 0
        updated = 0
        exported = 0

        if config is None:
            config = self._get_bitrix_config()
        deals_cutoff = fields.Datetime.now()

        try:
            deals = api.get_deals(config._pull_filter(config.deals_cursor))
        except Exception as error:
            if quiet:
                _logger.error("Bitrix24: fallo obteniendo deals: %s", error)
                return imported, updated, exported, 0, 0, []
            raise

        deals_by_id = {
            str(deal.get("ID")): deal
            for deal in deals
            if deal.get("ID")
        }

        for deal_id, deal in deals_by_id.items():
            values = self._deal_to_odoo_values(deal)
            existing = self.search(
                [("bitrix_deal_id", "=", deal_id)], limit=1
            )

            if not existing:
                self.create(dict(
                    values,
                    bitrix_deal_id=deal_id,
                    bitrix_last_sync=fields.Datetime.now(),
                ))
                imported += 1
                continue

            current = {
                "name": existing.name or "",
                "stage_id": existing.stage_id or False,
                "stage_semantic_id": existing.stage_semantic_id or False,
                "category_id": existing.category_id or False,
                "opportunity": existing.opportunity or 0.0,
                "currency_code": existing.currency_code or False,
                "assigned_by_id": existing.assigned_by_id or False,
                "partner_id": existing.partner_id.id or False,
                "company_id": existing.company_id.id or False,
            }

            incoming = {
                "name": values.get("name") or "",
                "stage_id": values.get("stage_id") or False,
                "stage_semantic_id": values.get("stage_semantic_id") or False,
                "category_id": values.get("category_id") or False,
                "opportunity": values.get("opportunity") or 0.0,
                "currency_code": values.get("currency_code") or False,
                "assigned_by_id": values.get("assigned_by_id") or False,
                "partner_id": values.get("partner_id") or False,
                "company_id": values.get("company_id") or False,
            }

            if current == incoming:
                continue

            existing.write(dict(
                values,
                bitrix_last_sync=fields.Datetime.now(),
            ))
            updated += 1

        config.deals_cursor = deals_cutoff
        projects_created, project_errors = self._ensure_won_projects(config)

        if not api:
            config = self._get_bitrix_config()
            api = BitrixAPI(config.webhook_url)

        unexported_deals = self.search([
            ("bitrix_deal_id", "=", False)
        ])

        for deal in unexported_deals:
            payload = {
                "TITLE": deal.name or "",
                "OPPORTUNITY": deal.opportunity or 0,
            }
            if deal.stage_id:
                payload["STAGE_ID"] = deal.stage_id
            if deal.partner_id and deal.partner_id.bitrix_contact_id:
                payload["CONTACT_ID"] = int(
                    deal.partner_id.bitrix_contact_id
                )
            if deal.company_id and deal.company_id.bitrix_company_id:
                payload["COMPANY_ID"] = int(
                    deal.company_id.bitrix_company_id
                )
            originator = config._originator_id()
            origin_id = f"deal_{deal.id}"
            payload.update({
                "ORIGINATOR_ID": originator,
                "ORIGIN_ID": origin_id,
            })
            success, new_id, error = config._push_record(
                deal, "crm.deal.add", payload,
                lambda: api.find_by_origin("deal", originator, origin_id)
                or api.create_deal(payload),
            )
            if error:
                project_errors.append(f"Negocio Odoo {deal.id}: {error}")
            elif success:
                deal.bitrix_deal_id = str(new_id)
                deal.bitrix_last_sync = fields.Datetime.now()
                exported += 1

        projects_exported, export_errors = self.env[
            "eigr.construction.project"
        ].sync_progress_with_bitrix(api, config)
        project_errors.extend(export_errors)

        return (
            imported, updated, exported, projects_created,
            projects_exported, project_errors,
        )
