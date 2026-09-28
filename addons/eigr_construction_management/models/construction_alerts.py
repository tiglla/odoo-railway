from odoo import api, fields, models


REQUIREMENT_APPROVAL = "EIGR: aprobar requerimiento"
DELIVERY_OVERDUE = "EIGR: entrega de requerimiento atrasada"
CLOSURE_OVERDUE = "EIGR: completar expediente de cierre"


class EigrConstructionProjectAlerts(models.Model):
    _inherit = "eigr.construction.project"

    @api.model
    def _sync_eigr_activity(self, record, summary, user, deadline, needed):
        Activity = self.env["mail.activity"].sudo()
        model = self.env["ir.model"].sudo().search(
            [("model", "=", record._name)], limit=1
        )
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        existing = Activity.search([
            ("res_model_id", "=", model.id),
            ("res_id", "=", record.id),
            ("activity_type_id", "=", activity_type.id),
            ("summary", "=", summary),
            ("automated", "=", True),
        ])
        if not needed or not user:
            existing.unlink()
            return

        values = {
            "user_id": user.id,
            "date_deadline": deadline,
        }
        if existing:
            if (
                existing[:1].user_id.id != user.id
                or existing[:1].date_deadline != deadline
            ):
                existing[:1].write(values)
            (existing - existing[:1]).unlink()
        else:
            Activity.create({
                **values,
                "res_model_id": model.id,
                "res_id": record.id,
                "activity_type_id": activity_type.id,
                "summary": summary,
                "automated": True,
            })

    @api.model
    def _cron_update_eigr_activities(self):
        today = fields.Date.today()
        admin = self.env.ref("base.user_admin")

        requirements = self.env["eigr.construction.requirement"].sudo().search([])
        for requirement in requirements:
            active = (
                requirement.project_id.active
                and requirement.project_id.state not in ("closed", "cancelled")
            )
            manager = (
                requirement.project_id.control_manager_id
                or requirement.project_id.responsible_id
                or admin
            )
            self._sync_eigr_activity(
                requirement,
                REQUIREMENT_APPROVAL,
                manager,
                today,
                active and requirement.state == "submitted",
            )
            delivery_date = (
                requirement.expected_delivery_date or requirement.required_date
            )
            self._sync_eigr_activity(
                requirement,
                DELIVERY_OVERDUE,
                manager,
                delivery_date,
                active
                and requirement.state in ("ordered", "partial")
                and delivery_date < today,
            )

        closures = self.env["eigr.construction.closure"].sudo().search([])
        for closure in closures:
            self._sync_eigr_activity(
                closure,
                CLOSURE_OVERDUE,
                closure.responsible_id or admin,
                closure.target_date,
                closure.project_id.active
                and closure.project_id.state == "closing"
                and closure.state in ("draft", "review")
                and closure.target_date <= today
                and closure.completion_percent < 100,
            )
