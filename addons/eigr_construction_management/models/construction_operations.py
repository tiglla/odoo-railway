from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class EigrConstructionOperation(models.AbstractModel):
    _name = "eigr.construction.operation"
    _description = "Registro operativo de obra EIGR"

    project_id = fields.Many2one(
        "eigr.construction.project", string="Obra", required=True,
        ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(
        related="project_id.company_id", store=True, index=True,
    )
    currency_id = fields.Many2one(related="project_id.currency_id")
    date = fields.Date(string="Fecha", default=fields.Date.context_today)
    notes = fields.Text(string="Observaciones")


class EigrConstructionTechnicalFile(models.Model):
    _name = "eigr.construction.technical_file"
    _description = "Expediente técnico de obra EIGR"
    _inherit = ["eigr.construction.operation", "mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Expediente", required=True, tracking=True)
    code = fields.Char(string="Código", required=True, default="Nuevo", readonly=True)
    file_type = fields.Selection([
        ("study", "Estudio definitivo"),
        ("project", "Proyecto"),
        ("additional", "Adicional"),
        ("other", "Otro"),
    ], string="Tipo", required=True, default="study")
    version = fields.Integer(string="Versión", required=True, default=1)
    state = fields.Selection([
        ("draft", "Borrador"),
        ("submitted", "En revisión"),
        ("approved", "Aprobado"),
        ("rejected", "Observado"),
    ], required=True, default="draft", tracking=True)
    approver_id = fields.Many2one("res.users", string="Aprobado por", readonly=True)
    approval_date = fields.Date(string="Fecha de aprobación", readonly=True)
    attachment_ids = fields.Many2many("ir.attachment", string="Documentos")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "Nuevo") == "Nuevo":
                vals["code"] = (
                    self.env["ir.sequence"].next_by_code(
                        "eigr.construction.technical_file"
                    ) or "Nuevo"
                )
        return super().create(vals_list)

    @api.constrains("version")
    def _check_version(self):
        if any(record.version < 1 for record in self):
            raise ValidationError("La versión debe ser mayor que cero.")

    def write(self, vals):
        if not self.env.su and not self.env.user.has_group(
            "eigr_construction_management.group_eigr_admin"
        ):
            if any(record.state == "approved" for record in self):
                raise AccessError("Solo el administrador puede editar un expediente aprobado.")
            if "state" in vals and vals["state"] != "submitted":
                raise AccessError("Use las acciones de revisión del expediente.")
            if "state" in vals:
                if any(record.state not in ("draft", "rejected") for record in self):
                    raise UserError("Solo un expediente borrador u observado puede enviarse.")
                if any(not record.attachment_ids for record in self):
                    raise UserError("Adjunte al menos un documento antes de enviar.")
        return super().write(vals)

    def action_submit(self):
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_planner"
        ):
            raise AccessError("Solo Planeamiento puede enviar expedientes técnicos.")
        if any(record.state not in ("draft", "rejected") for record in self):
            raise UserError("Solo un expediente borrador u observado puede enviarse.")
        if any(not record.attachment_ids for record in self):
            raise UserError("Adjunte al menos un documento antes de enviar.")
        self.write({"state": "submitted"})
        return True

    def action_approve(self):
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_manager"
        ):
            raise AccessError("Solo el Jefe de Control puede aprobar expedientes.")
        self.check_access("read")
        if any(record.state != "submitted" for record in self):
            raise UserError("Solo un expediente enviado puede aprobarse.")
        if any(not record.attachment_ids for record in self):
            raise UserError("El expediente debe conservar sus documentos para aprobarse.")
        self.sudo().write({
            "state": "approved",
            "approver_id": self.env.user.id,
            "approval_date": fields.Date.context_today(self),
        })
        return True

    def action_reject(self):
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_manager"
        ):
            raise AccessError("Solo el Jefe de Control puede observar expedientes.")
        self.check_access("read")
        if any(record.state != "submitted" for record in self):
            raise UserError("Solo un expediente enviado puede observarse.")
        self.sudo().write({"state": "rejected"})
        return True


class EigrConstructionSchedule(models.Model):
    _name = "eigr.construction.schedule"
    _description = "Cronograma de obra EIGR"
    _inherit = ["eigr.construction.operation", "mail.thread"]
    _order = "start_date, id"

    name = fields.Char(string="Actividad", required=True, tracking=True)
    code = fields.Char(string="Código")
    start_date = fields.Date(string="Inicio", required=True)
    end_date = fields.Date(string="Fin", required=True)
    weight_percent = fields.Float(string="Peso (%)")
    planned_percent = fields.Float(string="Avance planificado (%)")
    actual_percent = fields.Float(string="Avance real (%)")

    @api.constrains("start_date", "end_date", "weight_percent", "planned_percent", "actual_percent")
    def _check_schedule(self):
        for record in self:
            if record.end_date < record.start_date:
                raise ValidationError("El fin no puede ser anterior al inicio.")
            if any(not 0 <= value <= 100 for value in (
                record.weight_percent, record.planned_percent, record.actual_percent
            )):
                raise ValidationError("Los porcentajes deben estar entre 0 y 100.")


class EigrConstructionIncident(models.Model):
    _name = "eigr.construction.incident"
    _description = "Incidencia de obra EIGR"
    _inherit = ["eigr.construction.operation", "mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Incidencia", required=True, tracking=True)
    incident_type = fields.Selection([
        ("work", "De obra"), ("accident", "Accidente"),
        ("weather", "Clima"), ("material", "Materiales"),
        ("inspection", "Inspección"), ("other", "Otro"),
    ], required=True, default="work")
    reported_by_id = fields.Many2one(
        "res.users", string="Reportado por", default=lambda self: self.env.user,
    )
    state = fields.Selection([
        ("open", "Abierta"),
        ("in_progress", "En atención"),
        ("closed", "Cerrada"),
    ], required=True, default="open", tracking=True)

    def _check_resident_or_manager(self):
        if not any(self.env.user.has_group(group) for group in (
            "eigr_construction_management.group_eigr_resident",
            "eigr_construction_management.group_eigr_manager",
        )):
            raise AccessError("Solo el Residente o Jefe de Control gestiona incidencias.")

    def write(self, vals):
        if "state" in vals and not self.env.su and not self.env.user.has_group(
            "eigr_construction_management.group_eigr_admin"
        ):
            allowed = {"open": "in_progress", "in_progress": "closed"}
            if any(allowed.get(record.state) != vals["state"] for record in self):
                raise AccessError("Use las acciones de atención de incidencias.")
        return super().write(vals)

    def action_start(self):
        self._check_resident_or_manager()
        self.check_access("read")
        if any(record.state != "open" for record in self):
            raise UserError("Solo una incidencia abierta puede iniciarse.")
        self.sudo().write({"state": "in_progress"})
        return True

    def action_close(self):
        self._check_resident_or_manager()
        self.check_access("read")
        if any(record.state != "in_progress" for record in self):
            raise UserError("Solo una incidencia en atención puede cerrarse.")
        self.sudo().write({"state": "closed"})
        return True


class EigrConstructionDocument(models.Model):
    _name = "eigr.construction.document"
    _description = "Documento de obra EIGR"
    _inherit = ["eigr.construction.operation", "mail.thread"]
    _order = "date desc, id desc"

    name = fields.Char(string="Documento", required=True, tracking=True)
    doc_type = fields.Selection([
        ("contract", "Contrato"), ("resolution", "Resolución"),
        ("report", "Informe"), ("measurement", "Acta de medición"),
        ("technical", "Expediente técnico"), ("legal", "Legal"),
        ("other", "Otro"),
    ], required=True, default="other")
    reference = fields.Char(string="Referencia")
    attachment_ids = fields.Many2many("ir.attachment", string="Archivos")
