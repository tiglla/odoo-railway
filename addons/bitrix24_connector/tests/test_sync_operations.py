from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from odoo import fields
from odoo.tests.common import TransactionCase

from ..services.bitrix_api import BitrixAPI


class TestSyncOperations(TransactionCase):
    def test_timeline_marker_is_found_before_reposting(self):
        api = BitrixAPI("https://example.test/rest/1/token")
        api.call = Mock(return_value={"result": [
            {"ID": "7", "COMMENT": "Avance aprobado\n[EIGR:valuation-42]"},
        ]})
        self.assertTrue(api.has_timeline_marker("501", "[EIGR:valuation-42]"))
        self.assertEqual(
            api.call.call_args.args[1]["filter"],
            {"ENTITY_ID": 501, "ENTITY_TYPE": "deal"},
        )

    def test_incremental_filter_is_sent_to_bitrix(self):
        Config = self.env["bitrix.config"]
        cursor = datetime(2026, 9, 28, 12, 0, 0)
        extra = Config._pull_filter(cursor)
        self.assertEqual(
            extra["filter"][">=DATE_MODIFY"], "2026-09-28T11:58:00Z"
        )
        api = BitrixAPI("https://example.test/rest/1/token")
        api.call = Mock(return_value={"result": []})
        api.get_contacts(extra)
        self.assertEqual(
            api.call.call_args.args[1]["filter"], extra["filter"]
        )
        api.call.return_value = {"result": [{"ID": "77"}]}
        self.assertEqual(api.find_by_origin("contact", "ODOO_EIGR_test", "contact_8"), "77")

    def test_failed_push_is_logged_and_retried_when_due(self):
        config = self.env["bitrix.config"].create({
            "webhook_url": "https://example.test/rest/1/token"
        })
        partner = self.env["res.partner"].create({"name": "Cliente prueba"})
        payload = {"NAME": partner.name}
        failure = Mock(side_effect=ValueError("Correo inválido"))

        success, _result, error = config._push_record(
            partner, "crm.contact.add", payload, failure
        )
        self.assertFalse(success)
        self.assertIn("Correo inválido", error)
        Log = self.env["bitrix.sync.log"].sudo()
        log_domain = [
            ("config_id", "=", config.id),
            ("resource_model", "=", "res.partner"),
            ("resource_id", "=", partner.id),
            ("operation", "=", "crm.contact.add"),
        ]
        failed = Log.search(log_domain, limit=1)
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.attempts, 1)
        self.assertIn("Cliente prueba", failed.payload_json)
        self.assertNotIn(partner.id, config._due_retry_ids(
            "res.partner", "crm.contact"
        ))

        success, _result, error = config._push_record(
            partner, "crm.contact.add", payload, failure
        )
        self.assertFalse(success)
        self.assertIsNone(error)
        self.assertEqual(failure.call_count, 1)

        failed.write({
            "next_retry": fields.Datetime.now() - timedelta(seconds=1)
        })
        self.assertIn(partner.id, config._due_retry_ids(
            "res.partner", "crm.contact"
        ))
        success, result, error = config._push_record(
            partner, "crm.contact.add", payload, lambda: 777
        )
        self.assertTrue(success)
        self.assertEqual(result, 777)
        self.assertIsNone(error)
        self.assertEqual(failed.status, "retried")
        latest = Log.search(log_domain, limit=1)
        self.assertEqual(latest.status, "success")
        self.assertEqual(latest.attempts, 2)

    def test_project_fields_can_be_prepared_in_bitrix(self):
        config = self.env["bitrix.config"].create({
            "webhook_url": "https://example.test/rest/1/token"
        })
        with patch.object(BitrixAPI, "get_deal_userfields", return_value=[]), \
             patch.object(BitrixAPI, "create_deal_userfield", return_value=1) as create:
            config.action_setup_project_fields()
        self.assertEqual(create.call_count, 9)
        self.assertEqual(config.deal_field_project_code, "UF_CRM_EIGR_OBRA_CODIGO")
        self.assertEqual(config.deal_field_project_progress, "UF_CRM_EIGR_OBRA_AVANCE")
        self.assertEqual(config.deal_field_next_milestone, "UF_CRM_EIGR_PROXIMO_HITO")
        self.assertEqual(config.deal_field_progress_update, "UF_CRM_EIGR_ACTUALIZACION")
