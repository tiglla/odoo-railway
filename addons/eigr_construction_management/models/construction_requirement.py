from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class EigrConstructionRequirement(models.Model):
    _name = "eigr.construction.requirement"
    _description = "Requerimiento de Obra EIGR"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, required_date, id desc"

    name = fields.Char(string="Asunto", required=True, tracking=True)
    code = fields.Char(string="Código", required=True, default="Nuevo", tracking=True)
    project_id = fields.Many2one(
        "eigr.construction.project",
        string="Obra",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
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
    requester_id = fields.Many2one(
        "res.users",
        string="Solicitante",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
        check_company=True,
    )
    request_date = fields.Date(
        string="Fecha de solicitud",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    required_date = fields.Date(
        string="Fecha requerida en obra",
        required=True,
        tracking=True,
    )
    priority = fields.Selection(
        [("0", "Normal"), ("1", "Alta"), ("2", "Urgente")],
        string="Prioridad",
        default="0",
        required=True,
        tracking=True,
    )
    delivery_location = fields.Char(string="Lugar de entrega", tracking=True)
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("submitted", "Enviado"),
            ("approved", "Aprobado"),
            ("ordered", "Ordenado"),
            ("partial", "Recepción parcial"),
            ("received", "Recibido"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado",
        required=True,
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many(
        "eigr.construction.requirement.line",
        "requirement_id",
        string="Recursos solicitados",
        copy=True,
    )
    line_count = fields.Integer(
        string="Cantidad de items",
        compute="_compute_line_count",
    )
    estimated_total = fields.Monetary(
        string="Costo estimado",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    ordered_total = fields.Monetary(
        string="Costo ordenado",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    received_total = fields.Monetary(
        string="Valor recibido",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    receipt_progress = fields.Float(
        string="Recepción (%)",
        compute="_compute_totals",
        store=True,
    )
    approved_by_id = fields.Many2one(
        "res.users",
        string="Aprobado por",
        readonly=True,
        tracking=True,
    )
    approval_date = fields.Datetime(
        string="Fecha de aprobación",
        readonly=True,
        tracking=True,
    )
    vendor_id = fields.Many2one(
        "res.partner",
        string="Proveedor",
        tracking=True,
    )
    purchase_reference = fields.Char(
        string="Orden de compra / servicio",
        tracking=True,
    )
    purchase_date = fields.Date(string="Fecha de orden", tracking=True)
    expected_delivery_date = fields.Date(string="Entrega comprometida", tracking=True)
    receipt_reference = fields.Char(string="Guia o acta de recepción", tracking=True)
    receipt_date = fields.Date(string="Fecha de recepción total", readonly=True, tracking=True)
    notes = fields.Html(string="Justificacion y observaciones")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "Nuevo") == "Nuevo":
                vals["code"] = (
                    self.env["ir.sequence"].next_by_code("eigr.construction.requirement")
                    or "Nuevo"
                )
        return super().create(vals_list)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for requirement in self:
            requirement.line_count = len(requirement.line_ids)

    @api.depends(
        "line_ids.estimated_subtotal",
        "line_ids.ordered_subtotal",
        "line_ids.received_subtotal",
    )
    def _compute_totals(self):
        for requirement in self:
            requirement.estimated_total = sum(
                requirement.line_ids.mapped("estimated_subtotal")
            )
            requirement.ordered_total = sum(
                requirement.line_ids.mapped("ordered_subtotal")
            )
            requirement.received_total = sum(
                requirement.line_ids.mapped("received_subtotal")
            )
            requirement.receipt_progress = (
                requirement.received_total / requirement.ordered_total * 100
                if requirement.ordered_total
                else 0.0
            )

    @api.constrains("request_date", "required_date")
    def _check_required_date(self):
        for requirement in self:
            if requirement.required_date < requirement.request_date:
                raise ValidationError(
                    "La fecha requerida no puede ser anterior a la solicitud."
                )

    @api.constrains("purchase_date", "expected_delivery_date")
    def _check_purchase_dates(self):
        for requirement in self:
            if (
                requirement.purchase_date
                and requirement.expected_delivery_date
                and requirement.expected_delivery_date < requirement.purchase_date
            ):
                raise ValidationError(
                    "La entrega comprometida no puede ser anterior a la orden."
                )

    def _check_manager(self):
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_manager"
        ):
            raise AccessError("Solo el Jefe de Control puede realizar esta operacion.")

    def action_submit(self):
        invalid = self.filtered(lambda requirement: requirement.state != "draft")
        if invalid:
            raise UserError("Solo un requerimiento borrador puede enviarse.")
        for requirement in self:
            if requirement.project_id.state not in ("startup", "planning", "execution"):
                raise UserError(
                    "La obra debe estar en Arranque, Planificación o Ejecución."
                )
            if not requirement.line_ids:
                raise UserError("Agregue al menos un recurso al requerimiento.")
        self.write({"state": "submitted"})
        return True

    def action_approve(self):
        self._check_manager()
        invalid = self.filtered(lambda requirement: requirement.state != "submitted")
        if invalid:
            raise UserError("Solo un requerimiento enviado puede aprobarse.")
        self.sudo().write(
            {
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approval_date": fields.Datetime.now(),
            }
        )
        return True

    def action_reset_draft(self):
        self._check_manager()
        invalid = self.filtered(lambda requirement: requirement.state != "submitted")
        if invalid:
            raise UserError("Solo un requerimiento enviado puede volver a borrador.")
        self.sudo().write({"state": "draft"})
        return True

    def action_mark_ordered(self):
        self._check_manager()
        invalid = self.filtered(lambda requirement: requirement.state != "approved")
        if invalid:
            raise UserError("Solo un requerimiento aprobado puede marcarse como ordenado.")
        for requirement in self:
            if not requirement.vendor_id or not requirement.purchase_reference:
                raise UserError("Registre el proveedor y la referencia de compra.")
            if not requirement.purchase_date or not requirement.expected_delivery_date:
                raise UserError("Registre las fechas de orden y entrega comprometida.")
            if any(
                line.quantity_ordered <= 0 or line.actual_unit_cost <= 0
                for line in requirement.line_ids
            ):
                raise UserError(
                    "Todas las lineas deben tener cantidad ordenada y costo unitario real."
                )
        self.sudo().write({"state": "ordered"})
        return True

    def action_update_receipt(self):
        invalid = self.filtered(
            lambda requirement: requirement.state not in ("ordered", "partial")
        )
        if invalid:
            raise UserError("La recepción solo se actualiza en requerimientos ordenados.")
        for requirement in self:
            received_any = any(line.quantity_received > 0 for line in requirement.line_ids)
            received_all = all(
                line.quantity_received == line.quantity_ordered
                for line in requirement.line_ids
            )
            if not received_any:
                raise UserError("Registre al menos una cantidad recibida.")
            if received_all:
                if not requirement.receipt_reference:
                    raise UserError("Registre la guia o acta de recepción.")
                requirement.write(
                    {
                        "state": "received",
                        "receipt_date": fields.Date.context_today(self),
                    }
                )
            else:
                requirement.write({"state": "partial"})
        return True

    def action_cancel(self):
        self._check_manager()
        invalid = self.filtered(
            lambda requirement: requirement.state in ("received", "cancelled")
        )
        if invalid:
            raise UserError("Un requerimiento recibido o cancelado no puede cancelarse.")
        self.sudo().write({"state": "cancelled"})
        return True

    def write(self, vals):
        if (
            not self.env.su
            and not self.env.user.has_group(
                "eigr_construction_management.group_eigr_admin"
            )
            and self.env.user.has_group(
                "eigr_construction_management.group_eigr_manager"
            )
            and not self.env.user.has_group(
                "eigr_construction_management.group_eigr_resident"
            )
        ):
            purchase_fields = {
                "vendor_id",
                "purchase_reference",
                "purchase_date",
                "expected_delivery_date",
                "line_ids",
            }
            if set(vals) <= purchase_fields and all(
                requirement.state == "approved" for requirement in self
            ):
                return super().write(vals)
            raise AccessError(
                "El Jefe de Control solo puede aprobar y registrar los datos de compra."
            )
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda requirement: requirement.state != "draft"):
            raise UserError("Solo puede eliminarse un requerimiento borrador.")
        return super().unlink()


class EigrConstructionRequirementLine(models.Model):
    _name = "eigr.construction.requirement.line"
    _description = "Recurso Solicitado EIGR"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    requirement_id = fields.Many2one(
        "eigr.construction.requirement",
        string="Requerimiento",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="requirement_id.company_id", store=True)
    currency_id = fields.Many2one(related="requirement_id.currency_id", store=True)
    item_type = fields.Selection(
        [
            ("material", "Material"),
            ("equipment", "Equipo"),
            ("service", "Servicio"),
            ("subcontract", "Subcontrato"),
        ],
        string="Tipo",
        required=True,
        default="material",
    )
    name = fields.Char(string="Descripción", required=True)
    specification = fields.Char(string="Especificación")
    unit = fields.Selection(
        [
            ("glb", "Global"),
            ("und", "Unidad"),
            ("m", "Metro"),
            ("m2", "Metro cuadrado"),
            ("m3", "Metro cubico"),
            ("kg", "Kilogramo"),
            ("bol", "Bolsa"),
            ("dia", "Dia"),
            ("mes", "Mes"),
        ],
        string="Unidad",
        required=True,
        default="und",
    )
    quantity_requested = fields.Float(
        string="Cantidad solicitada",
        required=True,
        digits=(16, 3),
        default=1.0,
    )
    estimated_unit_cost = fields.Monetary(
        string="Costo unitario estimado",
        currency_field="currency_id",
        default=0.0,
    )
    estimated_subtotal = fields.Monetary(
        string="Costo estimado",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    quantity_ordered = fields.Float(
        string="Cantidad ordenada",
        digits=(16, 3),
        default=0.0,
    )
    actual_unit_cost = fields.Monetary(
        string="Costo unitario real",
        currency_field="currency_id",
        default=0.0,
    )
    ordered_subtotal = fields.Monetary(
        string="Costo ordenado",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    quantity_received = fields.Float(
        string="Cantidad recibida",
        digits=(16, 3),
        default=0.0,
    )
    received_subtotal = fields.Monetary(
        string="Valor recibido",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )

    @api.depends(
        "quantity_requested",
        "estimated_unit_cost",
        "quantity_ordered",
        "actual_unit_cost",
        "quantity_received",
    )
    def _compute_amounts(self):
        for line in self:
            line.estimated_subtotal = line.quantity_requested * line.estimated_unit_cost
            line.ordered_subtotal = line.quantity_ordered * line.actual_unit_cost
            line.received_subtotal = line.quantity_received * line.actual_unit_cost

    @api.constrains(
        "quantity_requested",
        "quantity_ordered",
        "quantity_received",
        "estimated_unit_cost",
        "actual_unit_cost",
    )
    def _check_quantities_and_costs(self):
        for line in self:
            if line.quantity_requested <= 0:
                raise ValidationError("La cantidad solicitada debe ser mayor que cero.")
            if line.quantity_ordered < 0 or line.quantity_received < 0:
                raise ValidationError("Las cantidades no pueden ser negativas.")
            if line.quantity_ordered > line.quantity_requested:
                raise ValidationError(
                    "La cantidad ordenada no puede superar la cantidad solicitada."
                )
            if line.quantity_received > line.quantity_ordered:
                raise ValidationError(
                    "La cantidad recibida no puede superar la cantidad ordenada."
                )
            if line.estimated_unit_cost < 0 or line.actual_unit_cost < 0:
                raise ValidationError("Los costos no pueden ser negativos.")

    @api.model_create_multi
    def create(self, vals_list):
        requirements = self.env["eigr.construction.requirement"].browse(
            [vals.get("requirement_id") for vals in vals_list if vals.get("requirement_id")]
        )
        if requirements.filtered(lambda requirement: requirement.state != "draft"):
            raise UserError("Solo se agregan recursos a un requerimiento borrador.")
        return super().create(vals_list)

    def write(self, vals):
        for line in self:
            state = line.requirement_id.state
            changed = set(vals)
            if state == "draft":
                continue
            if state == "approved" and changed <= {
                "quantity_ordered",
                "actual_unit_cost",
            }:
                if not self.env.user.has_group(
                    "eigr_construction_management.group_eigr_manager"
                ):
                    raise AccessError("Solo el Jefe de Control registra la compra.")
                continue
            if state in ("ordered", "partial") and changed <= {"quantity_received"}:
                continue
            raise UserError("La linea no puede modificarse en el estado actual.")
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.requirement_id.state != "draft"):
            raise UserError("Solo se eliminan recursos de un requerimiento borrador.")
        return super().unlink()
