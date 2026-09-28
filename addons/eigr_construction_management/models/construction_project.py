from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class EigrConstructionProject(models.Model):
    _name = "eigr.construction.project"
    _description = "Obra EIGR"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "code desc, id desc"

    name = fields.Char(string="Nombre de la obra", required=True, tracking=True)
    code = fields.Char(string="Código", required=True, default="Nuevo", tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Moneda",
        readonly=True,
    )
    client_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        tracking=True,
        check_company=True,
    )
    contract_number = fields.Char(string="Número de contrato", tracking=True)
    contract_amount = fields.Monetary(
        string="Monto contractual",
        currency_field="currency_id",
        tracking=True,
    )
    location = fields.Char(string="Ubicación", tracking=True)
    responsible_id = fields.Many2one(
        "res.users",
        string="Responsable general",
        default=lambda self: self.env.user,
        tracking=True,
        check_company=True,
    )
    control_manager_id = fields.Many2one(
        "res.users",
        string="Jefe de Control",
        tracking=True,
        check_company=True,
    )
    planning_engineer_id = fields.Many2one(
        "res.users",
        string="Ingeniero de Planeamiento",
        tracking=True,
        check_company=True,
    )
    resident_id = fields.Many2one(
        "res.users",
        string="Residente de obra",
        tracking=True,
        check_company=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("startup", "Arranque"),
            ("planning", "Planificación"),
            ("execution", "Ejecución"),
            ("closing", "Cierre"),
            ("closed", "Cerrada"),
            ("cancelled", "Cancelada"),
        ],
        string="Estado",
        required=True,
        default="draft",
        tracking=True,
    )
    planned_start_date = fields.Date(string="Inicio planificado", tracking=True)
    planned_end_date = fields.Date(string="Fin planificado", tracking=True)
    actual_start_date = fields.Date(string="Inicio real", tracking=True)
    actual_end_date = fields.Date(string="Fin real", tracking=True)
    progress_percent = fields.Float(
        string="Avance físico (%)",
        default=0.0,
        tracking=True,
    )
    budget_ids = fields.One2many(
        "eigr.construction.budget",
        "project_id",
        string="Presupuestos",
    )
    budget_count = fields.Integer(
        string="Número de presupuestos",
        compute="_compute_budget_summary",
    )
    approved_budget_id = fields.Many2one(
        "eigr.construction.budget",
        string="Presupuesto Meta",
        compute="_compute_budget_summary",
    )
    approved_budget_cost = fields.Monetary(
        string="Costo Meta",
        currency_field="currency_id",
        compute="_compute_budget_summary",
    )
    approved_budget_sale = fields.Monetary(
        string="Venta Meta",
        currency_field="currency_id",
        compute="_compute_budget_summary",
    )
    valuation_ids = fields.One2many(
        "eigr.construction.valuation",
        "project_id",
        string="Valorizaciónes",
    )
    valuation_count = fields.Integer(
        string="Número de valorizaciónes",
        compute="_compute_valuation_summary",
    )
    latest_valuation_id = fields.Many2one(
        "eigr.construction.valuation",
        string="Ultima valorización aprobada",
        compute="_compute_valuation_summary",
    )
    requirement_ids = fields.One2many(
        "eigr.construction.requirement",
        "project_id",
        string="Requerimientos",
    )
    requirement_count = fields.Integer(
        string="Número de requerimientos",
        compute="_compute_requirement_count",
    )
    closure_id = fields.Many2one(
        "eigr.construction.closure",
        string="Expediente de cierre",
        compute="_compute_closure",
    )
    closure_progress = fields.Float(
        string="Cierre documental (%)",
        compute="_compute_closure",
    )
    active = fields.Boolean(default=True)
    notes = fields.Html(string="Descripción y observaciones")

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "El código de la obra debe ser unico.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "Nuevo") == "Nuevo":
                vals["code"] = (
                    self.env["ir.sequence"].next_by_code("eigr.construction.project")
                    or "Nuevo"
                )
        return super().create(vals_list)

    @api.depends(
        "budget_ids",
        "budget_ids.state",
        "budget_ids.amount_cost",
        "budget_ids.amount_sale",
    )
    def _compute_budget_summary(self):
        for project in self:
            project.budget_count = len(project.budget_ids)
            approved = project.budget_ids.filtered(lambda budget: budget.state == "approved")[:1]
            project.approved_budget_id = approved
            project.approved_budget_cost = approved.amount_cost if approved else 0.0
            project.approved_budget_sale = approved.amount_sale if approved else 0.0

    def action_view_budgets(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "eigr_construction_management.action_eigr_construction_budget"
        )
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = {"default_project_id": self.id}
        return action

    @api.depends("valuation_ids", "valuation_ids.state", "valuation_ids.cutoff_date")
    def _compute_valuation_summary(self):
        for project in self:
            project.valuation_count = len(project.valuation_ids)
            approved = project.valuation_ids.filtered(
                lambda valuation: valuation.state == "approved"
            ).sorted("cutoff_date", reverse=True)[:1]
            project.latest_valuation_id = approved

    def action_view_valuations(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "eigr_construction_management.action_eigr_construction_valuation"
        )
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = {"default_project_id": self.id}
        return action

    @api.depends("requirement_ids")
    def _compute_requirement_count(self):
        for project in self:
            project.requirement_count = len(project.requirement_ids)

    def action_view_requirements(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "eigr_construction_management.action_eigr_construction_requirement"
        )
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = {"default_project_id": self.id}
        return action

    @api.depends("closure_ids", "closure_ids.completion_percent")
    def _compute_closure(self):
        for project in self:
            closure = project.closure_ids[:1]
            project.closure_id = closure
            project.closure_progress = closure.completion_percent if closure else 0.0

    closure_ids = fields.One2many(
        "eigr.construction.closure",
        "project_id",
        string="Expedientes de cierre",
    )

    def action_view_closure(self):
        self.ensure_one()
        if self.closure_id:
            return {
                "type": "ir.actions.act_window",
                "name": "Expediente de Cierre",
                "res_model": "eigr.construction.closure",
                "view_mode": "form",
                "res_id": self.closure_id.id,
            }
        action = self.env["ir.actions.actions"]._for_xml_id(
            "eigr_construction_management.action_eigr_construction_closure"
        )
        action["views"] = [(False, "form")]
        action["context"] = {"default_project_id": self.id}
        return action

    @api.constrains("planned_start_date", "planned_end_date")
    def _check_planned_dates(self):
        for project in self:
            if (
                project.planned_start_date
                and project.planned_end_date
                and project.planned_end_date < project.planned_start_date
            ):
                raise ValidationError(
                    "La fecha final planificada no puede ser anterior a la fecha inicial."
                )

    @api.constrains("actual_start_date", "actual_end_date")
    def _check_actual_dates(self):
        for project in self:
            if (
                project.actual_start_date
                and project.actual_end_date
                and project.actual_end_date < project.actual_start_date
            ):
                raise ValidationError(
                    "La fecha final real no puede ser anterior a la fecha inicial real."
                )

    @api.constrains("progress_percent")
    def _check_progress_percent(self):
        for project in self:
            if not 0 <= project.progress_percent <= 100:
                raise ValidationError("El avance físico debe estar entre 0 y 100 por ciento.")

    def _transition(self, expected_state, new_state, extra_values=None):
        is_responsible = self.env.user.has_group(
            "eigr_construction_management.group_eigr_responsible"
        )
        is_construction_admin = self.env.user.has_group(
            "eigr_construction_management.group_eigr_admin"
        )
        unauthorized = self.filtered(
            lambda project: not (self.env.is_admin() or is_construction_admin)
            and (not is_responsible or project.responsible_id != self.env.user)
        )
        if unauthorized:
            raise AccessError(
                "Solo el Responsable General asignado puede cambiar la etapa de la obra."
            )
        invalid = self.filtered(lambda project: project.state != expected_state)
        if invalid:
            raise UserError("La transicion solicitada no corresponde al estado actual.")
        values = {"state": new_state}
        values.update(extra_values or {})
        self.write(values)
        return True

    def action_startup(self):
        return self._transition("draft", "startup")

    def action_planning(self):
        for project in self:
            if not project.planned_start_date or not project.planned_end_date:
                raise UserError(
                    "Registre las fechas planificadas antes de iniciar la planificación."
                )
        return self._transition("startup", "planning")

    def action_execution(self):
        return self._transition(
            "planning",
            "execution",
            {"actual_start_date": fields.Date.context_today(self)},
        )

    def action_closing(self):
        return self._transition("execution", "closing")

    def action_close(self):
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_manager"
        ):
            raise AccessError("Solo el Jefe de Control puede aprobar el cierre.")
        incomplete = self.filtered(lambda project: project.progress_percent <= 99)
        if incomplete:
            raise UserError("El avance físico debe ser superior al 99% para cerrar la obra.")
        for project in self:
            if project.state != "closing":
                raise UserError("La obra debe estar en estado Cierre.")
            if not project.closure_ids.filtered(lambda closure: closure.state == "approved"):
                raise UserError("Primero debe aprobarse el expediente de cierre.")
        self.sudo().write(
            {
                "state": "closed",
                "actual_end_date": fields.Date.context_today(self),
            }
        )
        return True

    def action_cancel(self):
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_manager"
        ):
            raise AccessError("Solo el Jefe de Control puede cancelar una obra.")
        invalid = self.filtered(lambda project: project.state in ("closed", "cancelled"))
        if invalid:
            raise UserError("Una obra cerrada o cancelada no puede volver a cancelarse.")
        self.sudo().write({"state": "cancelled"})
        return True

    def action_reset_draft(self):
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_manager"
        ):
            raise AccessError("Solo el Jefe de Control puede devolver la obra a borrador.")
        invalid = self.filtered(lambda project: project.state != "cancelled")
        if invalid:
            raise UserError("Solo una obra cancelada puede volver a borrador.")
        self.sudo().write(
            {
                "state": "draft",
                "actual_start_date": False,
                "actual_end_date": False,
                "progress_percent": 0,
            }
        )
        return True
