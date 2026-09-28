from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare


class EigrRequirementPurchase(models.Model):
    _inherit = "eigr.construction.requirement"

    purchase_order_id = fields.Many2one(
        "purchase.order", string="Orden de compra Odoo", copy=False, readonly=True,
        check_company=True,
    )

    def write(self, vals):
        protected = {
            "vendor_id", "purchase_reference", "purchase_date",
            "expected_delivery_date", "receipt_reference", "receipt_date", "state",
            "purchase_order_id",
        }
        if (not (self.env.su and self.env.context.get("eigr_purchase_sync"))
                and protected & set(vals)
                and any(requirement.purchase_order_id for requirement in self)):
            raise UserError("Los datos de compra vinculados se actualizan desde Odoo.")
        return super().write(vals)

    def action_mark_ordered(self):
        if any(requirement.purchase_order_id for requirement in self):
            raise UserError("Confirme primero la orden de compra Odoo vinculada.")
        return super().action_mark_ordered()

    def action_update_receipt(self):
        if any(requirement.purchase_order_id for requirement in self):
            raise UserError("Valide la recepción en Inventario o actualice desde la compra.")
        return super().action_update_receipt()

    def action_create_purchase_order(self):
        self.ensure_one()
        self._check_manager()
        self.check_access("read")
        if self.state != "approved" or self.purchase_order_id:
            raise UserError("La compra solo puede generarse una vez desde un requerimiento aprobado.")
        if not self.vendor_id:
            raise UserError("Seleccione el proveedor antes de crear la solicitud de cotización.")
        if not self.line_ids or any(not line.product_id for line in self.line_ids):
            raise UserError("Asigne un producto Odoo a cada recurso solicitado.")
        self.project_id.action_setup_analytic_account()
        delivery_date = max(
            self.expected_delivery_date or self.required_date,
            fields.Date.context_today(self),
        )
        order = self.env["purchase.order"].with_company(self.company_id).create({
            "partner_id": self.vendor_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "origin": self.code,
            "order_line": [
                (0, 0, {
                    "eigr_requirement_line_id": line.id,
                    "product_id": line.product_id.id,
                    "name": line.name,
                    "product_qty": line.quantity_requested,
                    "product_uom_id": line.product_id.uom_po_id.id,
                    "price_unit": line.estimated_unit_cost,
                    "date_planned": fields.Datetime.to_datetime(delivery_date),
                    "analytic_distribution": (
                        {str(self.project_id.analytic_account_id.id): 100}
                        if self.project_id.analytic_account_id else False
                    ),
                }) for line in self.line_ids
            ],
        })
        for purchase_line in order.order_line:
            purchase_line.eigr_requirement_line_id.with_context(
                eigr_purchase_sync=True
            ).sudo().write({"purchase_line_id": purchase_line.id})
        self.sudo().write({"purchase_order_id": order.id})
        return {
            "type": "ir.actions.act_window",
            "name": "Solicitud de cotización",
            "res_model": "purchase.order",
            "view_mode": "form",
            "res_id": order.id,
        }

    def action_sync_purchase(self):
        self.check_access("read")
        for requirement in self.sudo().filtered("purchase_order_id"):
            order = requirement.purchase_order_id
            if order.state not in ("purchase", "done"):
                continue
            values = {
                "vendor_id": order.partner_id.id,
                "purchase_reference": order.name,
                "purchase_date": fields.Date.to_date(order.date_order),
                "expected_delivery_date": fields.Date.to_date(order.date_planned),
            }
            requirement.with_context(eigr_purchase_sync=True).sudo().write(values)
            for line in requirement.line_ids:
                purchase_line = line.purchase_line_id
                if not purchase_line or purchase_line.order_id != order:
                    raise UserError("Falta enlazar una línea del requerimiento con la orden.")
                target_uom = line.product_id.uom_po_id
                line.with_context(eigr_purchase_sync=True).sudo().write({
                    "quantity_ordered": purchase_line.product_uom_id._compute_quantity(
                        purchase_line.product_qty, target_uom
                    ),
                    "actual_unit_cost": order.currency_id._convert(
                        purchase_line.product_uom_id._compute_price(
                            purchase_line.price_unit_discounted, target_uom
                        ), requirement.currency_id,
                        requirement.company_id, fields.Date.to_date(order.date_order),
                    ),
                    "quantity_received": purchase_line.product_uom_id._compute_quantity(
                        purchase_line.qty_received, target_uom
                    ),
                })
            if requirement.state == "approved":
                requirement.with_context(eigr_purchase_sync=True).sudo().write({"state": "ordered"})
            if any(line.quantity_received > 0 for line in requirement.line_ids):
                pickings = order.picking_ids.filtered(lambda p: p.state == "done")
                if pickings:
                    requirement.with_context(eigr_purchase_sync=True).sudo().write({
                        "receipt_reference": ", ".join(pickings.mapped("name"))
                    })
                if all(float_compare(line.quantity_received, line.quantity_ordered,
                                     precision_digits=3) == 0 for line in requirement.line_ids):
                    requirement.with_context(eigr_purchase_sync=True).sudo().write({
                        "state": "received", "receipt_date": fields.Date.context_today(requirement),
                    })
                else:
                    requirement.with_context(eigr_purchase_sync=True).sudo().write({"state": "partial"})
            elif requirement.state in ("partial", "received"):
                requirement.with_context(eigr_purchase_sync=True).sudo().write({
                    "state": "ordered", "receipt_date": False, "receipt_reference": False,
                })
        return True

    def action_view_purchase_order(self):
        self.ensure_one()
        self.check_access("read")
        if not self.purchase_order_id:
            raise UserError("El requerimiento no tiene una orden de compra vinculada.")
        return {
            "type": "ir.actions.act_window",
            "name": "Orden de compra Odoo",
            "res_model": "purchase.order",
            "view_mode": "form",
            "res_id": self.purchase_order_id.id,
        }

    def action_cancel(self):
        if any(requirement.purchase_order_id and requirement.purchase_order_id.state != "cancel"
               for requirement in self):
            raise UserError("Cancele primero la orden de compra vinculada en Odoo.")
        return super().action_cancel()


class EigrRequirementPurchaseLine(models.Model):
    _inherit = "eigr.construction.requirement.line"

    product_id = fields.Many2one("product.product", string="Producto Odoo", check_company=True)
    purchase_line_id = fields.Many2one(
        "purchase.order.line", string="Línea de compra", copy=False, readonly=True,
        check_company=True,
    )

    def write(self, vals):
        if (not (self.env.su and self.env.context.get("eigr_purchase_sync"))
                and {"quantity_ordered", "quantity_received", "actual_unit_cost"} & set(vals)
                and any(line.purchase_line_id for line in self)):
            raise UserError("Las cantidades y el precio se actualizan desde la orden de compra.")
        return super().write(vals)


class EigrPurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def button_approve(self, force=False):
        result = super().button_approve(force=force)
        self.env["eigr.construction.requirement"].sudo().search([
            ("purchase_order_id", "in", self.ids)
        ]).action_sync_purchase()
        return result

    def button_confirm(self):
        result = super().button_confirm()
        self.env["eigr.construction.requirement"].sudo().search([
            ("purchase_order_id", "in", self.ids)
        ]).action_sync_purchase()
        return result

    def button_cancel(self):
        requirements = self.env["eigr.construction.requirement"].sudo().search([
            ("purchase_order_id", "in", self.ids)
        ])
        if any(line.quantity_received for line in requirements.line_ids):
            raise UserError("No se puede cancelar una compra con recursos ya recibidos en EIGR.")
        result = super().button_cancel()
        for requirement in requirements:
            requirement.line_ids.with_context(eigr_purchase_sync=True).sudo().write({
                "purchase_line_id": False,
                "quantity_ordered": 0,
                "actual_unit_cost": 0,
            })
            requirement.with_context(eigr_purchase_sync=True).sudo().write({
                "purchase_order_id": False,
                "purchase_reference": False,
                "purchase_date": False,
                "expected_delivery_date": False,
                "state": "approved",
            })
        return result


class EigrPurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    eigr_requirement_line_id = fields.Many2one(
        "eigr.construction.requirement.line", string="Recurso EIGR", copy=False,
        ondelete="restrict", check_company=True,
    )

    def write(self, vals):
        if "product_id" in vals and any(line.eigr_requirement_line_id for line in self):
            raise UserError("El producto de un recurso EIGR vinculado no puede cambiarse.")
        result = super().write(vals)
        if {"product_qty", "product_uom_id", "price_unit", "discount",
            "qty_received", "qty_received_manual", "date_planned"} & set(vals):
            self.mapped("eigr_requirement_line_id.requirement_id").sudo().action_sync_purchase()
        return result

    def unlink(self):
        if any(line.eigr_requirement_line_id and line.order_id.state != "cancel"
               for line in self):
            raise UserError("No elimine una línea vinculada a EIGR; cancele la orden completa.")
        return super().unlink()


class EigrStockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        result = super()._action_done()
        orders = self.mapped("purchase_id")
        if orders:
            self.env["eigr.construction.requirement"].sudo().search([
                ("purchase_order_id", "in", orders.ids)
            ]).action_sync_purchase()
        return result


class EigrProjectFinance(models.Model):
    _inherit = "eigr.construction.project"

    schedule_ids = fields.One2many("eigr.construction.schedule", "project_id", string="Cronograma")
    document_ids = fields.One2many("eigr.construction.document", "project_id", string="Documentos")
    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="Cuenta analítica de la obra", check_company=True,
    )
    posted_purchase_cost = fields.Monetary(
        string="Compras facturadas", currency_field="currency_id",
        compute="_compute_posted_purchase_cost",
    )
    purchase_cost_variance = fields.Monetary(
        string="Saldo frente al costo meta", currency_field="currency_id",
        compute="_compute_posted_purchase_cost",
    )

    @api.constrains("analytic_account_id")
    def _check_unique_analytic_account(self):
        for project in self.filtered("analytic_account_id"):
            duplicate = self.sudo().search_count([
                ("analytic_account_id", "=", project.analytic_account_id.id),
                ("id", "!=", project.id),
            ])
            if duplicate:
                raise ValidationError("Cada obra debe usar una cuenta analítica diferente.")

    def action_setup_analytic_account(self):
        if not any(self.env.user.has_group(group) for group in (
            "eigr_construction_management.group_eigr_responsible",
            "eigr_construction_management.group_eigr_manager",
        )):
            raise AccessError("Solo el Responsable General o Jefe de Control prepara la cuenta analítica.")
        self.check_access("read")
        for project in self:
            if not project.analytic_account_id:
                account = self.env["account.analytic.account"].sudo().create({
                    "name": f"{project.code} - {project.name}",
                    "plan_id": self.env.ref(
                        "eigr_construction_management.eigr_analytic_plan_works"
                    ).id,
                    "company_id": project.company_id.id,
                    "partner_id": project.client_id.id or False,
                })
                project.sudo().write({"analytic_account_id": account.id})
        return True

    def _compute_posted_purchase_cost(self):
        AnalyticLine = self.env["account.analytic.line"].sudo()
        for project in self:
            amount = 0.0
            if project.analytic_account_id:
                lines = AnalyticLine.search([
                    ("auto_account_id", "=", project.analytic_account_id.id),
                    ("move_line_id", "!=", False),
                    ("move_line_id.move_id.state", "=", "posted"),
                    ("move_line_id.move_id.move_type", "in", ("in_invoice", "in_refund")),
                    ("company_id", "=", project.company_id.id),
                ])
                amount = -sum(lines.mapped("amount"))
            project.posted_purchase_cost = amount
            project.purchase_cost_variance = project.approved_budget_cost - amount

    def action_open_purchase_costs(self):
        self.ensure_one()
        if not self.analytic_account_id:
            raise UserError("Asigne una cuenta analítica a la obra.")
        return {
            "type": "ir.actions.act_window",
            "name": "Costos de compra de la obra",
            "res_model": "account.analytic.line",
            "view_mode": "list,form",
            "domain": [
                ("auto_account_id", "=", self.analytic_account_id.id),
                ("move_line_id.move_id.state", "=", "posted"),
                ("move_line_id.move_id.move_type", "in", ("in_invoice", "in_refund")),
            ],
        }

    def get_client_photos(self):
        self.ensure_one()
        attachments = self.document_ids.filtered("client_approved").mapped("attachment_ids")
        return attachments.filtered(
            lambda attachment: attachment.mimetype and attachment.mimetype.startswith("image/")
        )[:3]

    def action_prepare_client_report(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "eigr_construction_management.group_eigr_responsible"
        ):
            raise AccessError("Solo el Responsable General prepara el informe para el cliente.")
        self.check_access("read")
        if not self.client_id or not self.client_id.email:
            raise UserError("Registre un cliente con correo electrónico para preparar el envío.")
        template = self.env.ref(
            "eigr_construction_management.email_template_eigr_client_progress"
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": self._name,
                "default_res_ids": self.ids,
                "default_composition_mode": "comment",
                "default_template_id": template.id,
            },
        }
