from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestEigrConstructionAlerts(TransactionCase):
    def test_pending_activities_are_unique_and_cleared(self):
        admin = self.env.ref("base.user_admin")
        today = fields.Date.today()
        project = self.env["eigr.construction.project"].create({
            "name": "Obra con avisos",
            "responsible_id": admin.id,
            "control_manager_id": admin.id,
            "state": "startup",
        })
        closing_project = self.env["eigr.construction.project"].create({
            "name": "Obra en cierre",
            "responsible_id": admin.id,
            "state": "closing",
        })
        requirement = self.env["eigr.construction.requirement"].create({
            "name": "Material pendiente",
            "project_id": project.id,
            "requester_id": admin.id,
            "required_date": today,
            "state": "submitted",
        })
        closure = self.env["eigr.construction.closure"].create({
            "name": "Cierre pendiente",
            "project_id": closing_project.id,
            "responsible_id": admin.id,
            "start_date": today - timedelta(days=2),
            "target_date": today - timedelta(days=1),
        })
        project._cron_update_eigr_activities()
        project._cron_update_eigr_activities()

        Activity = self.env["mail.activity"]
        approval = Activity.search([
            ("res_model_id.model", "=", requirement._name),
            ("res_id", "=", requirement.id),
            ("summary", "=", "EIGR: aprobar requerimiento"),
        ])
        closing = Activity.search([
            ("res_model_id.model", "=", closure._name),
            ("res_id", "=", closure.id),
            ("summary", "=", "EIGR: completar expediente de cierre"),
        ])
        self.assertEqual(len(approval), 1)
        self.assertEqual(len(closing), 1)
        self.assertEqual(approval.user_id, admin)

        requirement.write({
            "state": "ordered",
            "expected_delivery_date": today - timedelta(days=1),
        })
        project._cron_update_eigr_activities()
        self.assertFalse(approval.exists())
        delivery = Activity.search([
            ("res_model_id.model", "=", requirement._name),
            ("res_id", "=", requirement.id),
            ("summary", "=", "EIGR: entrega de requerimiento atrasada"),
        ])
        self.assertEqual(len(delivery), 1)

        requirement.write({"state": "received"})
        closure.write({"state": "approved"})
        project._cron_update_eigr_activities()
        self.assertFalse(delivery.exists())
        self.assertFalse(closing.exists())
