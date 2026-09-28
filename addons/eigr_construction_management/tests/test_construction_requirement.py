from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestEigrConstructionRequirement(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Requirement = cls.env["eigr.construction.requirement"]
        cls.team_user = cls.env["res.users"].create(
            {
                "name": "Solicitante EIGR",
                "login": "solicitante_eigr_test",
                "group_ids": [
                    Command.link(
                        cls.env.ref(
                            "eigr_construction_management.group_eigr_user"
                        ).id
                    )
                ],
            }
        )
        cls.project = cls.env["eigr.construction.project"].create(
            {
                "name": "Obra para requerimientos",
                "responsible_id": cls.team_user.id,
                "state": "startup",
                "planned_start_date": "2026-08-01",
                "planned_end_date": "2026-12-31",
            }
        )
        cls.vendor = cls.env["res.partner"].create(
            {"name": "Proveedor de Prueba EIGR", "is_company": True}
        )

    def _requirement_values(self, name="Requerimiento de prueba"):
        return {
            "name": name,
            "project_id": self.project.id,
            "requester_id": self.team_user.id,
            "request_date": "2026-08-01",
            "required_date": "2026-08-15",
            "line_ids": [
                Command.create(
                    {
                        "item_type": "material",
                        "name": "Material de prueba",
                        "unit": "und",
                        "quantity_requested": 10,
                        "estimated_unit_cost": 8,
                    }
                )
            ],
        }

    def _approve_and_prepare_order(self, requirement):
        requirement.action_submit()
        requirement.action_approve()
        requirement.write(
            {
                "vendor_id": self.vendor.id,
                "purchase_reference": "OC-TEST-001",
                "purchase_date": "2026-08-03",
                "expected_delivery_date": "2026-08-10",
            }
        )
        requirement.line_ids.write(
            {"quantity_ordered": 10, "actual_unit_cost": 9}
        )

    def test_sequence_and_estimated_total(self):
        requirement = self.Requirement.create(self._requirement_values())
        self.assertRegex(requirement.code, r"^REQ-\d{4}-\d{4}$")
        self.assertEqual(requirement.estimated_total, 80)
        self.assertEqual(requirement.line_count, 1)

    def test_complete_purchase_and_receipt_flow(self):
        requirement = self.Requirement.create(self._requirement_values())
        self._approve_and_prepare_order(requirement)
        requirement.action_mark_ordered()
        self.assertEqual(requirement.state, "ordered")
        self.assertEqual(requirement.ordered_total, 90)

        requirement.line_ids.quantity_received = 4
        requirement.action_update_receipt()
        self.assertEqual(requirement.state, "partial")
        self.assertEqual(requirement.receipt_progress, 40)

        requirement.line_ids.quantity_received = 10
        requirement.receipt_reference = "GR-TEST-001"
        requirement.action_update_receipt()
        self.assertEqual(requirement.state, "received")
        self.assertEqual(requirement.received_total, 90)
        self.assertEqual(requirement.receipt_progress, 100)
        self.assertTrue(requirement.receipt_date)

    def test_only_manager_can_approve(self):
        requirement = self.Requirement.create(self._requirement_values())
        requirement.action_submit()
        with self.assertRaises(AccessError):
            requirement.with_user(self.team_user).action_approve()

    def test_only_manager_records_purchase(self):
        requirement = self.Requirement.create(self._requirement_values())
        requirement.action_submit()
        requirement.action_approve()
        with self.assertRaises(AccessError):
            requirement.line_ids.with_user(self.team_user).write(
                {"quantity_ordered": 10, "actual_unit_cost": 9}
            )

    def test_submitted_resources_are_locked(self):
        requirement = self.Requirement.create(self._requirement_values())
        requirement.action_submit()
        with self.assertRaises(UserError):
            requirement.line_ids.quantity_requested = 9

    def test_reject_invalid_dates_and_quantities(self):
        values = self._requirement_values()
        values["required_date"] = "2026-07-31"
        with self.assertRaises(ValidationError):
            self.Requirement.create(values)

        requirement = self.Requirement.create(
            self._requirement_values("Requerimiento para cantidades")
        )
        with self.assertRaises(ValidationError):
            requirement.line_ids.quantity_ordered = 11

    def test_order_requires_supplier_and_reference(self):
        requirement = self.Requirement.create(self._requirement_values())
        requirement.action_submit()
        requirement.action_approve()
        with self.assertRaises(UserError):
            requirement.action_mark_ordered()

    def test_purchase_order_syncs_confirmed_quantities(self):
        product = self.env["product.product"].create({
            "name": "Material EIGR para compra", "purchase_ok": True,
        })
        requirement = self.Requirement.create(self._requirement_values())
        requirement.line_ids.product_id = product
        requirement.action_submit()
        requirement.action_approve()
        requirement.vendor_id = self.vendor
        action = requirement.action_create_purchase_order()
        order = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(requirement.purchase_order_id, order)
        self.assertEqual(requirement.line_ids.purchase_line_id.order_id, order)
        with self.assertRaises(UserError):
            requirement.line_ids.quantity_received = 1
        order.button_confirm()
        self.assertEqual(requirement.state, "ordered")
        self.assertEqual(requirement.purchase_reference, order.name)
        self.assertEqual(requirement.line_ids.quantity_ordered, 10)
        order.button_cancel()
        self.assertFalse(requirement.purchase_order_id)
        self.assertEqual(requirement.state, "approved")
