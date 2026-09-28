from unittest.mock import Mock, patch

from odoo import Command
from odoo.tests.common import TransactionCase

from ..services.bitrix_api import BitrixAPI


class TestWonDealProject(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Deal = cls.env["bitrix.deal"]
        cls.Project = cls.env["eigr.construction.project"]
        cls.config = cls.env["bitrix.config"].create({
            "name": "Bitrix24 test",
            "webhook_url": "https://example.test/rest/1/token",
            "project_responsible_id": cls.env.ref("base.user_admin").id,
        })
        cls.company = cls.env["res.partner"].create({
            "name": "Cliente Empresa",
            "is_company": True,
            "bitrix_company_id": "101",
        })

    def _sync(
        self, semantic, *, deal_id="501", company_id="101",
        contact_id=None, currency=None, assigned_by=None
    ):
        api = Mock()
        api.has_timeline_marker.return_value = False
        api.get_deal_userfields.return_value = [
            {"FIELD_NAME": name, "USER_TYPE_ID": field_type}
            for name, field_type in (
                (self.config.deal_field_project_code, "string"),
                (self.config.deal_field_project_state, "string"),
                (self.config.deal_field_project_progress, "double"),
                (self.config.deal_field_project_end_date, "date"),
                (self.config.deal_field_next_milestone, "string"),
                (self.config.deal_field_milestone_date, "date"),
                (self.config.deal_field_delay_days, "integer"),
                (self.config.deal_field_progress_update, "datetime"),
                (self.config.deal_field_client_contact, "date"),
            ) if name
        ]
        api.get_deals.return_value = [{
            "ID": deal_id,
            "TITLE": "Contrato de construcción",
            "STAGE_ID": "CUSTOM_STAGE",
            "STAGE_SEMANTIC_ID": semantic,
            "CATEGORY_ID": "2",
            "COMPANY_ID": company_id,
            "CONTACT_ID": contact_id,
            "OPPORTUNITY": 125000,
            "CURRENCY_ID": currency or self.env.company.currency_id.name,
            "ASSIGNED_BY_ID": assigned_by,
        }]
        result = self.Deal.sync_deals_with_bitrix(api, config=self.config)
        self.last_api = api
        return result

    def test_won_deal_creates_one_project_and_preserves_project_edits(self):
        self.assertIn("STAGE_SEMANTIC_ID", BitrixAPI.DEAL_SELECT)
        self._sync("P")
        self.assertFalse(self.Project.search([("bitrix_deal_id", "=", "501")]))
        self._sync("F")
        self.assertFalse(self.Project.search([("bitrix_deal_id", "=", "501")]))

        result = self._sync("S")
        project = self.Project.search([("bitrix_deal_id", "=", "501")])
        deal = self.Deal.search([("bitrix_deal_id", "=", "501")])
        self.assertEqual(result[3], 1)
        self.assertEqual(len(project), 1)
        self.assertEqual(project.state, "draft")
        self.assertEqual(project.client_id, self.company)
        self.assertEqual(project.contract_amount, 125000)
        self.assertEqual(deal.project_id, project)

        project.write({"name": "Nombre operativo", "contract_amount": 120000})
        self.assertEqual(self._sync("S")[3], 0)
        self.assertEqual(self.Project.search_count([
            ("bitrix_deal_id", "=", "501")
        ]), 1)
        self.assertEqual(project.name, "Nombre operativo")
        self.assertEqual(project.contract_amount, 120000)

    def test_contact_only_won_deal_uses_contact_as_client(self):
        contact = self.env["res.partner"].create({
            "name": "Cliente Persona",
            "bitrix_contact_id": "202",
        })
        result = self._sync(
            "S", deal_id="502", company_id=None, contact_id="202"
        )
        project = self.Project.search([("bitrix_deal_id", "=", "502")])
        self.assertEqual(result[3], 1)
        self.assertEqual(project.client_id, contact)

    def test_won_deal_without_client_is_reported_and_not_converted(self):
        result = self._sync("S", deal_id="503", company_id=None)
        self.assertEqual(result[3], 0)
        self.assertIn("503", result[5][0])
        self.assertFalse(self.Project.search([("bitrix_deal_id", "=", "503")]))

    def test_won_deal_with_different_currency_is_not_converted(self):
        currency = "USD" if self.env.company.currency_id.name != "USD" else "PEN"
        result = self._sync("S", deal_id="504", currency=currency)
        self.assertEqual(result[3], 0)
        self.assertIn("moneda", result[5][0])
        self.assertFalse(self.Project.search([("bitrix_deal_id", "=", "504")]))

    def test_existing_project_is_linked_without_creating_another(self):
        project = self.Project.create({
            "name": "Obra existente",
            "client_id": self.company.id,
            "bitrix_deal_id": "505",
        })
        result = self._sync("S", deal_id="505")
        deal = self.Deal.search([("bitrix_deal_id", "=", "505")])
        self.assertEqual(result[3], 0)
        self.assertEqual(deal.project_id, project)
        self.assertEqual(self.Project.search_count([
            ("bitrix_deal_id", "=", "505")
        ]), 1)

    def test_bitrix_salesperson_sets_project_responsible(self):
        self.config.user_mapping_ids = [Command.create({
            "bitrix_user_id": "88",
            "user_id": self.env.user.id,
        })]
        self._sync("S", deal_id="506", assigned_by="88")
        project = self.Project.search([("bitrix_deal_id", "=", "506")])
        self.assertEqual(project.responsible_id, self.env.user)

    def test_project_progress_is_sent_only_when_it_changes(self):
        self.config.write({
            "deal_field_project_code": "UF_CRM_EIGR_CODE",
            "deal_field_project_state": "UF_CRM_EIGR_STATE",
            "deal_field_project_progress": "UF_CRM_EIGR_PROGRESS",
            "deal_field_project_end_date": "UF_CRM_EIGR_END",
        })
        result = self._sync("S", deal_id="507")
        self.assertEqual(result[4], 1)
        self.last_api.update_deal.assert_called_once()
        payload = self.last_api.update_deal.call_args.args[1]
        self.assertEqual(payload["UF_CRM_EIGR_PROGRESS"], 0)
        self.assertEqual(self._sync("S", deal_id="507")[4], 0)
        project = self.Project.search([("bitrix_deal_id", "=", "507")])
        project.progress_percent = 35
        self.assertEqual(self._sync("S", deal_id="507")[4], 1)
        self.assertEqual(
            self.last_api.update_deal.call_args.args[1]["UF_CRM_EIGR_PROGRESS"],
            35,
        )

    def test_milestone_delay_and_phase_comment_are_sent_once(self):
        self.config.write({
            "deal_field_next_milestone": "UF_CRM_EIGR_PROXIMO_HITO",
            "deal_field_milestone_date": "UF_CRM_EIGR_FECHA_HITO",
            "deal_field_delay_days": "UF_CRM_EIGR_DIAS_ATRASO",
        })
        self._sync("S", deal_id="508")
        project = self.Project.search([("bitrix_deal_id", "=", "508")])
        self.env["eigr.construction.schedule"].create({
            "project_id": project.id,
            "name": "Entrega de estructura",
            "start_date": "2020-01-01",
            "end_date": "2020-01-02",
            "is_milestone": True,
        })
        project.state = "startup"
        self._sync("S", deal_id="508")
        payload = self.last_api.update_deal.call_args.args[1]
        self.assertEqual(payload["UF_CRM_EIGR_PROXIMO_HITO"], "Entrega de estructura")
        self.assertEqual(payload["UF_CRM_EIGR_FECHA_HITO"], "2020-01-02")
        self.assertGreater(payload["UF_CRM_EIGR_DIAS_ATRASO"], 0)
        self.last_api.add_timeline_comment.assert_called_once()
        self._sync("S", deal_id="508")
        self.last_api.add_timeline_comment.assert_not_called()

    def test_event_fetches_current_won_deal_and_its_company(self):
        api = Mock()
        api.get_deal.return_value = {
            "ID": "509", "TITLE": "Contrato nuevo", "STAGE_SEMANTIC_ID": "S",
            "COMPANY_ID": "101", "CURRENCY_ID": self.env.company.currency_id.name,
        }
        with patch.object(BitrixAPI, "get_deal", return_value=api.get_deal.return_value):
            self.Deal._sync_deal_event(self.config, "509")
        self.assertEqual(self.Project.search_count([("bitrix_deal_id", "=", "509")]), 1)

    def test_bitrix_notice_trigger_is_only_sent_in_bitrix_mode(self):
        self.config.deal_field_progress_update = "UF_CRM_EIGR_ACTUALIZACION"
        project = self.Project.create({"name": "Obra con aviso", "client_id": self.company.id})
        project.state = "startup"
        self.assertNotIn(
            "UF_CRM_EIGR_ACTUALIZACION", project._bitrix_progress_payload(self.config),
        )
        self.config.client_notification_mode = "bitrix"
        self.assertIn(
            "UF_CRM_EIGR_ACTUALIZACION", project._bitrix_progress_payload(self.config),
        )
