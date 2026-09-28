from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestBitrixSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.internal_user = cls.env["res.users"].create({
            "name": "Usuario interno sin administración Bitrix",
            "login": "bitrix_internal_security_test",
            "group_ids": [Command.link(cls.env.ref("base.group_user").id)],
        })
        cls.config = cls.env["bitrix.config"].create({
            "webhook_url": "https://example.test/rest/1/secret",
        })
        cls.deal = cls.env["bitrix.deal"].create({"name": "Negocio protegido"})

    def test_internal_user_cannot_read_or_change_connector_configuration(self):
        with self.assertRaises(AccessError):
            self.config.with_user(self.internal_user).read(["webhook_url"])
        with self.assertRaises(AccessError):
            self.config.with_user(self.internal_user).write({"active": False})
        with self.assertRaises(AccessError):
            self.env["bitrix.field.mapping"].with_user(self.internal_user).search([])

    def test_internal_user_cannot_forge_won_deals(self):
        with self.assertRaises(AccessError):
            self.deal.with_user(self.internal_user).read(["name"])
        with self.assertRaises(AccessError):
            self.env["bitrix.deal"].with_user(self.internal_user).create({
                "name": "Negocio falso", "stage_semantic_id": "S",
                "bitrix_deal_id": "999999",
            })
        with self.assertRaises(AccessError):
            self.deal.with_user(self.internal_user).write({"stage_semantic_id": "S"})

    def test_public_actions_check_admin_before_network_access(self):
        restricted = self.config.with_user(self.internal_user)
        for action in (
            restricted.action_sync_now,
            restricted.action_test_connection,
            restricted.action_import_contacts,
            restricted.action_setup_project_fields,
        ):
            with self.assertRaises(AccessError):
                action()
        with self.assertRaises(AccessError):
            self.env["res.partner"].with_user(self.internal_user).import_bitrix_contacts()
        with self.assertRaises(AccessError):
            self.env["res.partner"].with_user(self.internal_user).sync_with_bitrix(self.config)

    def test_bitrix_partner_identifiers_are_admin_only(self):
        partner = self.env["res.partner"].create({"name": "Cliente protegido"})
        with self.assertRaises(AccessError):
            partner.with_user(self.internal_user).read(["bitrix_contact_id"])
        self.assertTrue(self.env.ref("base.user_admin").has_group("base.group_system"))
        self.config.with_user(self.env.ref("base.user_admin")).check_access("write")
        self.assertEqual(
            self.env.ref("bitrix24_connector.access_bitrix_config_user").group_id,
            self.env.ref("base.group_system"),
        )
