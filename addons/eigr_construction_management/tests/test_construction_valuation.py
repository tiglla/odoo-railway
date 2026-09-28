from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestEigrConstructionValuation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Valuation = cls.env["eigr.construction.valuation"]
        cls.team_user = cls.env["res.users"].create(
            {
                "name": "Residente Valorizaciónes EIGR",
                "login": "residente_valorizaciónes_eigr_test",
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
                "name": "Obra para valorizaciónes",
                "responsible_id": cls.team_user.id,
                "state": "planning",
                "planned_start_date": "2026-08-01",
                "planned_end_date": "2026-12-31",
            }
        )
        cls.budget = cls.env["eigr.construction.budget"].create(
            {
                "name": "Presupuesto de valorizaciónes",
                "project_id": cls.project.id,
                "line_ids": [
                    Command.create(
                        {
                            "code": "01.01",
                            "name": "Concreto de prueba",
                            "unit": "m3",
                            "quantity": 10,
                            "unit_cost": 80,
                            "unit_price": 100,
                        }
                    )
                ],
            }
        )
        cls.budget.action_approve()
        cls.project.action_execution()
        cls.budget_line = cls.budget.line_ids

    def _valuation_values(
        self,
        name="Valorización 1",
        start="2026-08-01",
        cutoff="2026-08-31",
        planned=4,
        executed=3,
        actual_cost=250,
    ):
        return {
            "name": name,
            "project_id": self.project.id,
            "budget_id": self.budget.id,
            "period_start_date": start,
            "cutoff_date": cutoff,
            "line_ids": [
                Command.create(
                    {
                        "budget_line_id": self.budget_line.id,
                        "planned_quantity_period": planned,
                        "executed_quantity_period": executed,
                        "actual_cost_period": actual_cost,
                    }
                )
            ],
        }

    def test_compute_indicators_and_sequence(self):
        valuation = self.Valuation.create(self._valuation_values())
        self.assertRegex(valuation.code, r"^VAL-\d{4}-\d{4}$")
        self.assertEqual(valuation.planned_value, 400)
        self.assertEqual(valuation.executed_value, 300)
        self.assertEqual(valuation.valuation_period_amount, 300)
        self.assertEqual(valuation.planned_progress, 40)
        self.assertEqual(valuation.actual_progress, 30)
        self.assertEqual(valuation.schedule_variance, -10)
        self.assertAlmostEqual(valuation.cpi_percent, 250 / 320 * 100)

    def test_submit_approve_and_update_project(self):
        valuation = self.Valuation.create(self._valuation_values())
        valuation.action_submit()
        self.assertEqual(valuation.state, "submitted")
        valuation.action_approve()
        self.assertEqual(valuation.state, "approved")
        self.assertEqual(self.project.progress_percent, 30)
        self.assertEqual(self.project.latest_valuation_id, valuation)

    def test_accumulates_previous_approved_valuation(self):
        first = self.Valuation.create(self._valuation_values())
        first.action_submit()
        first.action_approve()
        second = self.Valuation.create(
            self._valuation_values(
                name="Valorización 2",
                start="2026-09-01",
                cutoff="2026-09-30",
                planned=3,
                executed=4,
                actual_cost=320,
            )
        )
        second.action_submit()
        line = second.line_ids
        self.assertEqual(line.planned_quantity_accumulated, 7)
        self.assertEqual(line.executed_quantity_accumulated, 7)
        self.assertEqual(line.actual_cost_accumulated, 570)
        self.assertEqual(second.valuation_period_amount, 400)
        self.assertEqual(second.actual_progress, 70)

    def test_out_of_order_approval_keeps_latest_project_progress(self):
        first = self.Valuation.create(self._valuation_values())
        first.action_submit()
        second = self.Valuation.create(
            self._valuation_values(
                name="Valorización posterior",
                start="2026-09-01",
                cutoff="2026-09-30",
                planned=4,
                executed=4,
                actual_cost=320,
            )
        )
        second.action_submit()
        second.action_approve()
        self.assertEqual(self.project.progress_percent, 40)
        with self.assertRaises(UserError):
            first.action_approve()
        self.assertEqual(first.state, "submitted")
        self.assertEqual(self.project.latest_valuation_id, second)
        self.assertEqual(self.project.progress_percent, 40)

    def test_cannot_submit_older_valuation_after_later_approval(self):
        later = self.Valuation.create(self._valuation_values(
            start="2026-09-01", cutoff="2026-09-30"
        ))
        later.action_submit()
        later.action_approve()
        older = self.Valuation.create(self._valuation_values(
            name="Valorización anterior",
            start="2026-08-01",
            cutoff="2026-08-31",
        ))
        with self.assertRaises(UserError):
            older.action_submit()

    def test_resubmits_stale_accumulated_values_before_approval(self):
        first = self.Valuation.create(self._valuation_values())
        first.action_submit()
        second = self.Valuation.create(self._valuation_values(
            name="Valorización posterior",
            start="2026-09-01",
            cutoff="2026-09-30",
            planned=3,
            executed=4,
            actual_cost=320,
        ))
        second.action_submit()
        first.action_approve()
        with self.assertRaises(UserError):
            second.action_approve()
        self.assertEqual(self.project.progress_percent, 30)
        second.action_reset_draft()
        second.action_submit()
        second.action_approve()
        self.assertEqual(self.project.progress_percent, 70)

    def test_reject_progress_above_budget(self):
        valuation = self.Valuation.create(
            self._valuation_values(planned=10, executed=11, actual_cost=900)
        )
        with self.assertRaises(UserError):
            valuation.action_submit()

    def test_only_manager_can_approve(self):
        valuation = self.Valuation.create(self._valuation_values())
        valuation.action_submit()
        with self.assertRaises(AccessError):
            valuation.with_user(self.team_user).action_approve()

    def test_submitted_lines_are_locked(self):
        valuation = self.Valuation.create(self._valuation_values())
        valuation.action_submit()
        with self.assertRaises(UserError):
            valuation.line_ids.executed_quantity_period = 4

    def test_reject_invalid_period_and_negative_values(self):
        values = self._valuation_values(start="2026-09-01", cutoff="2026-08-31")
        with self.assertRaises(ValidationError):
            self.Valuation.create(values)

        values = self._valuation_values(cutoff="2026-10-31", actual_cost=-1)
        with self.assertRaises(ValidationError):
            self.Valuation.create(values)
