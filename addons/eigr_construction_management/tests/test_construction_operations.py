from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestEigrConstructionOperations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["eigr.construction.project"].create({
            "name": "Obra operativa",
        })
        cls.team_user = cls.env["res.users"].create({
            "name": "Usuario de obra sin asignar",
            "login": "eigr_operations_unassigned_test",
            "group_ids": [Command.link(
                cls.env.ref("eigr_construction_management.group_eigr_user").id
            )],
        })
        cls.planner = cls.env["res.users"].create({
            "name": "Planeador EIGR",
            "login": "eigr_operations_planner_test",
            "group_ids": [Command.link(
                cls.env.ref("eigr_construction_management.group_eigr_planner").id
            )],
        })
        cls.project.planning_engineer_id = cls.planner

    def test_technical_file_requires_document_and_manager_approval(self):
        attachment = self.env["ir.attachment"].create({
            "name": "Plano de prueba.pdf",
            "type": "binary",
            "datas": "YQ==",
        })
        file = self.env["eigr.construction.technical_file"].create({
            "name": "Expediente de prueba",
            "project_id": self.project.id,
        })
        with self.assertRaises(UserError):
            file.action_submit()
        with self.assertRaises(AccessError):
            file.with_user(self.planner).write({"state": "approved"})
        file.attachment_ids = [Command.link(attachment.id)]
        file.action_submit()
        with self.assertRaises(AccessError):
            file.with_user(self.team_user).action_approve()
        file.action_approve()
        self.assertEqual(file.state, "approved")
        self.assertTrue(file.approval_date)
        with self.assertRaises(AccessError):
            file.with_user(self.planner).write({"name": "Alterado"})

    def test_schedule_dates_and_incident_flow(self):
        Schedule = self.env["eigr.construction.schedule"]
        with self.assertRaises(ValidationError):
            Schedule.create({
                "project_id": self.project.id,
                "name": "Actividad inválida",
                "start_date": "2026-10-10",
                "end_date": "2026-10-09",
            })
        incident = self.env["eigr.construction.incident"].create({
            "project_id": self.project.id,
            "name": "Incidencia de prueba",
        })
        incident.action_start()
        incident.action_close()
        self.assertEqual(incident.state, "closed")

    def test_unassigned_team_cannot_see_operational_records(self):
        document = self.env["eigr.construction.document"].create({
            "project_id": self.project.id,
            "name": "Documento de prueba",
        })
        visible = self.env["eigr.construction.document"].with_user(
            self.team_user
        ).search([("id", "=", document.id)])
        self.assertFalse(visible)

    def test_schedule_predecessor_and_delay(self):
        Schedule = self.env["eigr.construction.schedule"]
        first = Schedule.create({
            "project_id": self.project.id, "name": "Primera etapa",
            "start_date": "2026-01-01", "end_date": "2026-01-10",
            "is_milestone": True, "responsible_id": self.planner.id,
        })
        second = Schedule.create({
            "project_id": self.project.id, "name": "Segunda etapa",
            "start_date": "2026-01-11", "end_date": "2026-01-20",
            "predecessor_id": first.id,
        })
        with self.assertRaises(UserError):
            second.action_complete()
        first.action_complete()
        second.action_complete()
        self.assertEqual(second.actual_percent, 100)
        self.assertTrue(second.completion_date)
        with self.assertRaises(ValidationError):
            first.predecessor_id = second

    def test_client_photo_approval_resets_after_file_change(self):
        document = self.env["eigr.construction.document"].create({
            "project_id": self.project.id, "name": "Fotos de avance",
        })
        with self.assertRaises(UserError):
            document.action_approve_for_client()
        attachment = self.env["ir.attachment"].create({
            "name": "obra.png", "type": "binary", "datas": "YQ==",
            "mimetype": "image/png",
        })
        document.attachment_ids = [Command.link(attachment.id)]
        document.action_approve_for_client()
        self.assertTrue(document.client_approved)
        document.attachment_ids = [Command.clear()]
        self.assertFalse(document.client_approved)
