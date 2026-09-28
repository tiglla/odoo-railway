from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare


class EigrConstructionValuation(models.Model):
    _name = "eigr.construction.valuation"
    _description = "Valorización y Avance de Obra EIGR"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "cutoff_date desc, id desc"

    name = fields.Char(string="Valorización", required=True, tracking=True)
    code = fields.Char(string="Código", required=True, default="Nuevo", tracking=True)
    project_id = fields.Many2one(
        "eigr.construction.project",
        string="Obra",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    budget_id = fields.Many2one(
        "eigr.construction.budget",
        string="Presupuesto Meta",
        required=True,
        ondelete="restrict",
        tracking=True,
        domain="[('project_id', '=', project_id), ('state', '=', 'approved')]",
        check_company=True,
    )
    company_id = fields.Many2one(
        related="project_id.company_id",
        string="Empresa",
        store=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related="project_id.currency_id",
        string="Moneda",
        store=True,
    )
    period_start_date = fields.Date(
        string="Inicio del período",
        required=True,
        tracking=True,
    )
    cutoff_date = fields.Date(
        string="Fecha de corte",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("submitted", "Por aprobar"),
            ("approved", "Aprobada"),
            ("cancelled", "Cancelada"),
        ],
        string="Estado",
        required=True,
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many(
        "eigr.construction.valuation.line",
        "valuation_id",
        string="Avance por partida",
        copy=True,
    )
    line_count = fields.Integer(
        string="Cantidad de partidas",
        compute="_compute_line_count",
    )
    planned_value = fields.Monetary(
        string="Venta programada acumulada",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    executed_value = fields.Monetary(
        string="Venta producida acumulada",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    valuation_period_amount = fields.Monetary(
        string="Valorización del período",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    planned_cost = fields.Monetary(
        string="Costo programado acumulado",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    actual_cost = fields.Monetary(
        string="Costo real acumulado",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    actual_cost_period = fields.Monetary(
        string="Costo real del período",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    planned_progress = fields.Float(
        string="Avance planificado (%)",
        compute="_compute_totals",
        store=True,
    )
    actual_progress = fields.Float(
        string="Avance real (%)",
        compute="_compute_totals",
        store=True,
    )
    schedule_variance = fields.Float(
        string="Desviación de avance (pp)",
        compute="_compute_totals",
        store=True,
    )
    cpi_percent = fields.Float(
        string="CPI - Costo real/programado (%)",
        compute="_compute_totals",
        store=True,
    )
    approved_by_id = fields.Many2one(
        "res.users",
        string="Aprobada por",
        readonly=True,
        tracking=True,
    )
    approval_date = fields.Datetime(
        string="Fecha de aprobación",
        readonly=True,
        tracking=True,
    )
    notes = fields.Html(string="Resumen e incidencias del período")

    _project_cutoff_unique = models.Constraint(
        "UNIQUE(project_id, cutoff_date)",
        "Solo puede existir una valorización por obra y fecha de corte.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "Nuevo") == "Nuevo":
                vals["code"] = (
                    self.env["ir.sequence"].next_by_code("eigr.construction.valuation")
                    or "Nuevo"
                )
        return super().create(vals_list)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for valuation in self:
            valuation.line_count = len(valuation.line_ids)

    @api.depends(
        "line_ids.planned_value_accumulated",
        "line_ids.executed_value_accumulated",
        "line_ids.valuation_period_amount",
        "line_ids.planned_cost_accumulated",
        "line_ids.actual_cost_accumulated",
        "line_ids.actual_cost_period",
        "budget_id.amount_sale",
    )
    def _compute_totals(self):
        for valuation in self:
            valuation.planned_value = sum(
                valuation.line_ids.mapped("planned_value_accumulated")
            )
            valuation.executed_value = sum(
                valuation.line_ids.mapped("executed_value_accumulated")
            )
            valuation.valuation_period_amount = sum(
                valuation.line_ids.mapped("valuation_period_amount")
            )
            valuation.planned_cost = sum(
                valuation.line_ids.mapped("planned_cost_accumulated")
            )
            valuation.actual_cost = sum(
                valuation.line_ids.mapped("actual_cost_accumulated")
            )
            valuation.actual_cost_period = sum(
                valuation.line_ids.mapped("actual_cost_period")
            )
            budget_sale = valuation.budget_id.amount_sale
            valuation.planned_progress = (
                valuation.planned_value / budget_sale * 100 if budget_sale else 0.0
            )
            valuation.actual_progress = (
                valuation.executed_value / budget_sale * 100 if budget_sale else 0.0
            )
            valuation.schedule_variance = (
                valuation.actual_progress - valuation.planned_progress
            )
            valuation.cpi_percent = (
                valuation.actual_cost / valuation.planned_cost * 100
                if valuation.planned_cost
                else 0.0
            )

    @api.constrains("period_start_date", "cutoff_date")
    def _check_period_dates(self):
        for valuation in self:
            if valuation.period_start_date > valuation.cutoff_date:
                raise ValidationError(
                    "El inicio del período no puede ser posterior a la fecha de corte."
                )

    @api.onchange("project_id")
    def _onchange_project_id(self):
        self.budget_id = self.project_id.approved_budget_id

    def action_generate_lines(self):
        for valuation in self:
            if valuation.state != "draft":
                raise UserError("Las partidas solo se generan en una valorización borrador.")
            if not valuation.budget_id:
                raise UserError("Seleccióne el Presupuesto Meta.")
            existing = valuation.line_ids.mapped("budget_line_id")
            commands = [
                Command.create({"budget_line_id": line.id})
                for line in valuation.budget_id.line_ids
                if line not in existing
            ]
            if commands:
                valuation.write({"line_ids": commands})
        return True

    def _previous_approved_values(self, line):
        self.ensure_one()
        Line = self.env["eigr.construction.valuation.line"]
        previous = Line.search([
            ("valuation_id.project_id", "=", self.project_id.id),
            ("valuation_id.budget_id", "=", self.budget_id.id),
            ("valuation_id.state", "=", "approved"),
            ("valuation_id.cutoff_date", "<", self.cutoff_date),
            ("budget_line_id", "=", line.budget_line_id.id),
        ])
        return {
            "previous_planned_quantity": sum(previous.mapped("planned_quantity_period")),
            "previous_executed_quantity": sum(previous.mapped("executed_quantity_period")),
            "previous_actual_cost": sum(previous.mapped("actual_cost_period")),
        }

    def _snapshot_previous_values(self):
        for valuation in self:
            for line in valuation.line_ids:
                line.write(valuation._previous_approved_values(line))

    def _check_previous_snapshot(self):
        for valuation in self:
            for line in valuation.line_ids:
                expected = valuation._previous_approved_values(line)
                if any(
                    float_compare(line[field], value, precision_digits=3) != 0
                    for field, value in expected.items()
                ):
                    raise UserError(
                        "Se aprobó una valorización anterior después del envío. "
                        "Devuelva esta valorización a borrador y envíela nuevamente "
                        "para actualizar los acumulados."
                    )

    def _validate_progress(self):
        for valuation in self:
            if not valuation.line_ids:
                raise UserError("Genere y complete las partidas de la valorización.")
            for line in valuation.line_ids:
                if float_compare(
                    line.planned_quantity_accumulated,
                    line.budget_quantity,
                    precision_digits=3,
                ) > 0:
                    raise UserError(
                        f"El avance planificado de {line.budget_line_id.code} supera el metrado presupuestado."
                    )
                if float_compare(
                    line.executed_quantity_accumulated,
                    line.budget_quantity,
                    precision_digits=3,
                ) > 0:
                    raise UserError(
                        f"El avance ejecutado de {line.budget_line_id.code} supera el metrado presupuestado."
                    )

    def action_submit(self):
        invalid = self.filtered(lambda valuation: valuation.state != "draft")
        if invalid:
            raise UserError("Solo una valorización borrador puede enviarse a aprobación.")
        for valuation in self:
            valuation._check_approval_order()
            if valuation.project_id.state != "execution":
                raise UserError("La obra debe estar en Ejecución para valorizar avances.")
            if valuation.budget_id.state != "approved":
                raise UserError("La valorización requiere un Presupuesto Meta aprobado.")
        self._snapshot_previous_values()
        self._validate_progress()
        self.write({"state": "submitted"})
        return True

    def _check_approval_order(self):
        for valuation in self:
            later = self.search([
                ("project_id", "=", valuation.project_id.id),
                ("state", "=", "approved"),
                ("cutoff_date", ">", valuation.cutoff_date),
            ], limit=1)
            if later:
                raise UserError(
                    "No se puede aprobar una valorización con fecha de corte "
                    "anterior a otra ya aprobada."
                )

    def action_approve(self):
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_manager"
        ):
            raise AccessError("Solo el Jefe de Control puede aprobar valorizaciónes.")
        if len(self) != 1:
            raise UserError("Apruebe las valorizaciones una por una, por fecha de corte.")
        invalid = self.filtered(lambda valuation: valuation.state != "submitted")
        if invalid:
            raise UserError("Solo una valorización enviada puede aprobarse.")
        self._check_approval_order()
        self._check_previous_snapshot()
        self._validate_progress()
        self.sudo().write(
            {
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approval_date": fields.Datetime.now(),
            }
        )
        for project in self.mapped("project_id"):
            latest = project.latest_valuation_id
            project.sudo().write({"progress_percent": latest.actual_progress})
        return True

    def action_reset_draft(self):
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_manager"
        ):
            raise AccessError("Solo el Jefe de Control puede devolver la valorización.")
        invalid = self.filtered(lambda valuation: valuation.state != "submitted")
        if invalid:
            raise UserError("Solo una valorización por aprobar puede volver a borrador.")
        self.sudo().write({"state": "draft"})
        self.sudo().line_ids.write(
            {
                "previous_planned_quantity": 0,
                "previous_executed_quantity": 0,
                "previous_actual_cost": 0,
            }
        )
        return True

    def action_cancel(self):
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_manager"
        ):
            raise AccessError("Solo el Jefe de Control puede cancelar valorizaciónes.")
        invalid = self.filtered(
            lambda valuation: valuation.state not in ("draft", "submitted")
        )
        if invalid:
            raise UserError("Una valorización aprobada no puede cancelarse.")
        self.sudo().write({"state": "cancelled"})
        return True

    def unlink(self):
        if self.filtered(lambda valuation: valuation.state in ("submitted", "approved")):
            raise UserError("No se puede eliminar una valorización enviada o aprobada.")
        return super().unlink()


class EigrConstructionValuationLine(models.Model):
    _name = "eigr.construction.valuation.line"
    _description = "Avance por Partida EIGR"
    _order = "budget_line_id"

    valuation_id = fields.Many2one(
        "eigr.construction.valuation",
        string="Valorización",
        required=True,
        ondelete="cascade",
        index=True,
    )
    budget_line_id = fields.Many2one(
        "eigr.construction.budget.line",
        string="Partida",
        required=True,
        ondelete="restrict",
        domain="[('budget_id', '=', parent.budget_id)]",
    )
    company_id = fields.Many2one(related="valuation_id.company_id", store=True)
    currency_id = fields.Many2one(related="valuation_id.currency_id", store=True)
    budget_quantity = fields.Float(
        related="budget_line_id.quantity",
        string="Metrado Meta",
        digits=(16, 3),
        store=True,
    )
    unit = fields.Selection(related="budget_line_id.unit", string="Unidad", store=True)
    unit_cost = fields.Monetary(
        related="budget_line_id.unit_cost",
        string="Costo unitario Meta",
        currency_field="currency_id",
        store=True,
    )
    unit_price = fields.Monetary(
        related="budget_line_id.unit_price",
        string="Precio unitario",
        currency_field="currency_id",
        store=True,
    )
    planned_quantity_period = fields.Float(
        string="Metrado planificado período",
        digits=(16, 3),
        default=0.0,
    )
    executed_quantity_period = fields.Float(
        string="Metrado ejecutado período",
        digits=(16, 3),
        default=0.0,
    )
    actual_cost_period = fields.Monetary(
        string="Costo real período",
        currency_field="currency_id",
        default=0.0,
    )
    previous_planned_quantity = fields.Float(
        string="Planificado anterior",
        digits=(16, 3),
        readonly=True,
        default=0.0,
    )
    previous_executed_quantity = fields.Float(
        string="Ejecutado anterior",
        digits=(16, 3),
        readonly=True,
        default=0.0,
    )
    previous_actual_cost = fields.Monetary(
        string="Costo real anterior",
        currency_field="currency_id",
        readonly=True,
        default=0.0,
    )
    planned_quantity_accumulated = fields.Float(
        string="Planificado acumulado",
        digits=(16, 3),
        compute="_compute_amounts",
        store=True,
    )
    executed_quantity_accumulated = fields.Float(
        string="Ejecutado acumulado",
        digits=(16, 3),
        compute="_compute_amounts",
        store=True,
    )
    planned_value_accumulated = fields.Monetary(
        string="Venta programada acumulada",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    executed_value_accumulated = fields.Monetary(
        string="Venta producida acumulada",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    valuation_period_amount = fields.Monetary(
        string="Valorización período",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    planned_cost_accumulated = fields.Monetary(
        string="Costo programado acumulado",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    actual_cost_accumulated = fields.Monetary(
        string="Costo real acumulado",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    progress_percent = fields.Float(
        string="Avance de partida (%)",
        compute="_compute_amounts",
        store=True,
    )

    _valuation_line_unique = models.Constraint(
        "UNIQUE(valuation_id, budget_line_id)",
        "La partida solo puede aparecer una vez en la valorización.",
    )

    @api.depends(
        "planned_quantity_period",
        "executed_quantity_period",
        "actual_cost_period",
        "previous_planned_quantity",
        "previous_executed_quantity",
        "previous_actual_cost",
        "budget_quantity",
        "unit_cost",
        "unit_price",
    )
    def _compute_amounts(self):
        for line in self:
            line.planned_quantity_accumulated = (
                line.previous_planned_quantity + line.planned_quantity_period
            )
            line.executed_quantity_accumulated = (
                line.previous_executed_quantity + line.executed_quantity_period
            )
            line.planned_value_accumulated = (
                line.planned_quantity_accumulated * line.unit_price
            )
            line.executed_value_accumulated = (
                line.executed_quantity_accumulated * line.unit_price
            )
            line.valuation_period_amount = line.executed_quantity_period * line.unit_price
            line.planned_cost_accumulated = (
                line.planned_quantity_accumulated * line.unit_cost
            )
            line.actual_cost_accumulated = (
                line.previous_actual_cost + line.actual_cost_period
            )
            line.progress_percent = (
                line.executed_quantity_accumulated / line.budget_quantity * 100
                if line.budget_quantity
                else 0.0
            )

    @api.constrains(
        "planned_quantity_period",
        "executed_quantity_period",
        "actual_cost_period",
    )
    def _check_nonnegative_values(self):
        for line in self:
            if line.planned_quantity_period < 0 or line.executed_quantity_period < 0:
                raise ValidationError("Los metrados del período no pueden ser negativos.")
            if line.actual_cost_period < 0:
                raise ValidationError("El costo real del período no puede ser negativo.")

    def _check_valuation_editable(self):
        if self.filtered(lambda line: line.valuation_id.state != "draft"):
            raise UserError("El avance solo puede editarse en una valorización borrador.")

    @api.model_create_multi
    def create(self, vals_list):
        valuations = self.env["eigr.construction.valuation"].browse(
            [vals.get("valuation_id") for vals in vals_list if vals.get("valuation_id")]
        )
        if valuations.filtered(lambda valuation: valuation.state != "draft"):
            raise UserError("No se pueden agregar partidas a esta valorización.")
        return super().create(vals_list)

    def write(self, vals):
        self._check_valuation_editable()
        return super().write(vals)

    def unlink(self):
        self._check_valuation_editable()
        return super().unlink()
