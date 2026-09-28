from unittest.mock import Mock

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
        contact_id=None, currency=None
    ):
        api = Mock()
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
        }]
        return self.Deal.sync_deals_with_bitrix(api, config=self.config)

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
        self.assertIn("503", result[4][0])
        self.assertFalse(self.Project.search([("bitrix_deal_id", "=", "503")]))

    def test_won_deal_with_different_currency_is_not_converted(self):
        currency = "USD" if self.env.company.currency_id.name != "USD" else "PEN"
        result = self._sync("S", deal_id="504", currency=currency)
        self.assertEqual(result[3], 0)
        self.assertIn("moneda", result[4][0])
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
