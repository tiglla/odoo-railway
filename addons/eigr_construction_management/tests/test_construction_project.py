from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestEigrConstructionProject(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Project = cls.env["eigr.construction.project"]
        cls.team_user = cls.env["res.users"].create(
            {
                "name": "Usuario Equipo EIGR",
                "login": "equipo_eigr_test",
                "group_ids": [
                    Command.link(
                        cls.env.ref(
                            "eigr_construction_management.group_eigr_user"
                        ).id
                    )
                ],
            }
        )

    def _project_values(self, suffix="TEST"):
        return {
            "name": "Obra demostrativa",
            "code": f"EIGR-{suffix}",
            "responsible_id": self.team_user.id,
            "planned_start_date": "2026-08-01",
            "planned_end_date": "2026-12-31",
        }

    def test_sequence_and_default_state(self):
        project = self.Project.create({"name": "Obra con correlativo"})
        self.assertRegex(project.code, r"^EIGR-\d{4}-\d{4}$")
        self.assertEqual(project.state, "draft")

    def test_complete_lifecycle(self):
        project = self.Project.create(self._project_values("LIFE"))
        project.action_startup()
        project.action_planning()
        project.action_execution()
        self.assertTrue(project.actual_start_date)
        project.progress_percent = 100
        project.action_closing()
        project.action_close()
        self.assertEqual(project.state, "closed")
        self.assertTrue(project.actual_end_date)

    def test_reject_invalid_transition(self):
        project = self.Project.create(self._project_values("TRANS"))
        with self.assertRaises(UserError):
            project.action_execution()

    def test_only_manager_can_close(self):
        project = self.Project.create(self._project_values("SEC"))
        project.write({"state": "closing", "progress_percent": 100})
        with self.assertRaises(AccessError):
            project.with_user(self.team_user).action_close()

    def test_odoo_administrator_controls_unassigned_project(self):
        administrator = self.env.ref("base.user_admin")
        self.assertTrue(administrator.has_group(
            "eigr_construction_management.group_eigr_admin"
        ))
        project = self.Project.with_user(administrator).create(
            self._project_values("ADMIN")
        )
        project.with_user(administrator).action_startup()
        self.assertEqual(project.state, "startup")
        project.with_user(administrator).write({"name": "Obra administrada"})
        self.assertEqual(project.name, "Obra administrada")

    def test_reject_invalid_dates_and_progress(self):
        invalid_dates = self._project_values("DATES")
        invalid_dates.update(
            {
                "planned_start_date": "2026-12-31",
                "planned_end_date": "2026-08-01",
            }
        )
        with self.assertRaises(ValidationError):
            self.Project.create(invalid_dates)

        project = self.Project.create(self._project_values("PROGRESS"))
        with self.assertRaises(ValidationError):
            project.progress_percent = 101
