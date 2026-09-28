import logging
from datetime import datetime, timezone

from odoo import models, fields, _
from odoo.exceptions import UserError

from ..services.bitrix_api import BitrixAPI

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):

    _inherit = "res.partner"

    bitrix_contact_id = fields.Char(
        string="Bitrix24 Contact ID",
        index=True,
        copy=False,
    )

    bitrix_company_id = fields.Char(
        string="Bitrix24 Company ID",
        index=True,
        copy=False,
    )

    bitrix_last_sync = fields.Datetime(
        string="Última sincronización Bitrix24",
        readonly=True,
    )

    _bitrix_company_id_unique = models.Constraint(
        "unique(bitrix_company_id)",
        "El ID de la empresa de Bitrix24 debe ser único.",
    )

    _bitrix_contact_id_unique = models.Constraint(
        "unique(bitrix_contact_id)",
        "El ID del contacto de Bitrix24 debe ser único.",
    )

    def _get_bitrix_config(self):

        config = self.env[
            "bitrix.config"
        ].search(
            [
                ("active", "=", True)
            ],
            limit=1,
        )

        if not config:
            raise UserError(
                _(
                    "No existe una configuración activa "
                    "de Bitrix24."
                )
            )

        return config

    @staticmethod
    def _parse_bitrix_date(value):

        if not value:
            return False

        try:

            parsed = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )

        except ValueError:

            return False

        if parsed.tzinfo is not None:

            parsed = parsed.astimezone(
                timezone.utc
            ).replace(tzinfo=None)

        return parsed

    @staticmethod
    def _bitrix_to_odoo_values(contact):

        bitrix_id = str(contact.get("ID") or "")

        name = " ".join(
            part
            for part in [
                contact.get("NAME") or "",
                contact.get("SECOND_NAME") or "",
                contact.get("LAST_NAME") or "",
            ]
            if part
        ).strip()

        if not name:
            name = f"Bitrix Contact {bitrix_id}"

        return {
            "name": name,
            "phone": ResPartner._get_multifield_value(
                contact.get("PHONE")
            ) or False,
            "email": ResPartner._get_multifield_value(
                contact.get("EMAIL")
            ) or False,
        }

    @staticmethod
    def _odoo_to_sync_values(partner):

        return {
            "name": partner.name or "",
            "phone": partner.phone or False,
            "email": partner.email or False,
        }

    @staticmethod
    def _odoo_values_to_bitrix(values):

        payload = {
            "NAME": values.get("name") or "",
        }

        if values.get("phone"):

            payload["PHONE"] = [
                {
                    "VALUE": values["phone"],
                    "VALUE_TYPE": "WORK",
                }
            ]

        if values.get("email"):

            payload["EMAIL"] = [
                {
                    "VALUE": values["email"],
                    "VALUE_TYPE": "WORK",
                }
            ]

        return payload

    def _pull_bitrix_contacts(self, contacts_by_id):

        imported = 0
        updated = 0
        pulled_ids = set()

        for bitrix_id, contact in contacts_by_id.items():

            values = self._bitrix_to_odoo_values(contact)

            partner = self.search(
                [("bitrix_contact_id", "=", bitrix_id)],
                limit=1,
            )

            if not partner:

                partner = self.create(dict(
                    values,
                    bitrix_contact_id=bitrix_id,
                    bitrix_last_sync=fields.Datetime.now(),
                ))

                imported += 1
                pulled_ids.add(partner.id)

                continue

            if self._odoo_to_sync_values(partner) == values:
                continue

            bitrix_date = self._parse_bitrix_date(
                contact.get("DATE_MODIFY")
            )

            if (
                bitrix_date
                and partner.write_date
                and bitrix_date <= partner.write_date
            ):
                continue

            partner.write(dict(
                values,
                bitrix_last_sync=fields.Datetime.now(),
            ))

            pulled_ids.add(partner.id)
            updated += 1

        return imported, updated, pulled_ids

    def _push_bitrix_contacts(
        self, api, contacts_by_id, pulled_ids, config
    ):

        domain = [("type", "=", "contact"), ("is_company", "=", False)]

        if pulled_ids:

            domain.append(
                ("id", "not in", list(pulled_ids))
            )

        if config.last_sync:
            domain += ["|", ("bitrix_contact_id", "=", False),
                       ("write_date", ">", config.last_sync)]
        candidates = self.search(domain)
        due_ids = config._due_retry_ids("res.partner", "crm.contact")
        if due_ids:
            candidates |= self.search([
                ("type", "=", "contact"), ("is_company", "=", False),
                ("id", "in", due_ids)
            ])

        exported = 0
        errors = []

        for partner in candidates:
            if partner.id in pulled_ids:
                continue

            values = self._odoo_to_sync_values(partner)
            bitrix_id = partner.bitrix_contact_id

            if bitrix_id and bitrix_id in contacts_by_id:

                if values == self._bitrix_to_odoo_values(
                    contacts_by_id[bitrix_id]
                ):
                    continue

            payload = self._odoo_values_to_bitrix(values)

            if not bitrix_id:
                originator = config._originator_id()
                origin_id = f"contact_{partner.id}"
                payload.update({
                    "ORIGINATOR_ID": originator,
                    "ORIGIN_ID": origin_id,
                })

            operation = "crm.contact.update" if bitrix_id else "crm.contact.add"
            send = (
                (lambda: api.update_contact(bitrix_id, payload))
                if bitrix_id else (
                    lambda: api.find_by_origin("contact", originator, origin_id)
                    or api.create_contact(payload)
                )
            )
            success, result, error = config._push_record(
                partner, operation, payload, send
            )
            if error:
                message = (
                    f"Contacto Odoo {partner.id} ({partner.name}), "
                    f"correo {partner.email or 'vacío'}: {error}"
                )
                _logger.warning("Bitrix24: %s", message)
                errors.append(message)
                continue
            if not success:
                continue

            if not bitrix_id:
                partner.bitrix_contact_id = str(result)

            partner.bitrix_last_sync = fields.Datetime.now()

            exported += 1

        return exported, errors

    def sync_with_bitrix(self, config):

        api = BitrixAPI(config.webhook_url)

        contacts_cutoff = fields.Datetime.now()
        contacts = api.get_contacts(config._pull_filter(config.contacts_cursor))

        contacts_by_id = {
            str(contact.get("ID")): contact
            for contact in contacts
            if contact.get("ID")
        }

        imported, updated, pulled_ids = (
            self._pull_bitrix_contacts(contacts_by_id)
        )
        config.contacts_cursor = contacts_cutoff

        exported, contact_errors = self._push_bitrix_contacts(
            api, contacts_by_id, pulled_ids, config
        )

        companies_imported, companies_updated, companies_exported, company_errors = (
            self.sync_companies_with_bitrix(api, config)
        )

        deals_imported, deals_updated, deals_exported, projects_created, projects_exported, project_errors = (
            self.env["bitrix.deal"].sync_deals_with_bitrix(
                api, quiet=False, config=config
            )
        )

        config.last_sync = fields.Datetime.now()

        return {
            "imported": imported,
            "updated": updated,
            "exported": exported,
            "companies_imported": companies_imported,
            "companies_updated": companies_updated,
            "companies_exported": companies_exported,
            "deals_imported": deals_imported,
            "deals_updated": deals_updated,
            "deals_exported": deals_exported,
            "projects_created": projects_created,
            "projects_exported": projects_exported,
            "sync_errors": contact_errors + company_errors + project_errors,
        }

    def import_bitrix_contacts(self):

        config = self._get_bitrix_config()

        api = BitrixAPI(config.webhook_url)

        try:
            contacts = api.get_contacts()

        except Exception as error:
            raise UserError(
                _("Error conectando con Bitrix24: %s") % error
            )

        contacts_by_id = {
            str(contact.get("ID")): contact
            for contact in contacts
            if contact.get("ID")
        }

        imported, updated, _pulled = (
            self._pull_bitrix_contacts(contacts_by_id)
        )

        config.last_sync = fields.Datetime.now()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bitrix24"),
                "message": _(
                    "Importación completada. "
                    "Nuevos: %s | Actualizados: %s"
                ) % (
                    imported,
                    updated,
                ),
                "type": "success",
                "sticky": False,
            },
        }

    @staticmethod
    def _get_multifield_value(values):

        if not values:
            return False

        if isinstance(values, list):

            if not values:
                return False

            first = values[0]

            if isinstance(first, dict):
                return first.get("VALUE")

            return first

        return values

    @staticmethod
    def _bitrix_to_odoo_company(company):

        bitrix_id = str(company.get("ID") or "")
        title = (company.get("TITLE") or "").strip()

        if not title:
            title = f"Bitrix Company {bitrix_id}"

        return {
            "name": title,
            "is_company": True,
            "phone": ResPartner._get_multifield_value(
                company.get("PHONE")
            ) or False,
            "email": ResPartner._get_multifield_value(
                company.get("EMAIL")
            ) or False,
        }

    @staticmethod
    def _company_to_odoo_sync(partner):

        return {
            "name": partner.name or "",
            "is_company": partner.is_company,
            "phone": partner.phone or False,
            "email": partner.email or False,
        }

    def _pull_bitrix_companies(self, companies):

        imported = 0
        updated = 0
        pulled_ids = set()

        for company in companies:

            bitrix_id = str(company.get("ID") or "")

            if not bitrix_id:
                continue

            values = self._bitrix_to_odoo_company(company)

            partner = self.search(
                [("bitrix_company_id", "=", bitrix_id)],
                limit=1,
            )

            if not partner:

                partner = self.create(dict(
                    values,
                    bitrix_company_id=bitrix_id,
                    bitrix_last_sync=fields.Datetime.now(),
                ))

                imported += 1
                pulled_ids.add(partner.id)
                continue

            if self._company_to_odoo_sync(partner) == values:
                continue

            bitrix_date = self._parse_bitrix_date(
                company.get("DATE_MODIFY")
            )

            if (
                bitrix_date
                and partner.write_date
                and bitrix_date <= partner.write_date
            ):
                continue

            partner.write(dict(
                values,
                bitrix_last_sync=fields.Datetime.now(),
            ))

            pulled_ids.add(partner.id)
            updated += 1

        return imported, updated, pulled_ids

    def _push_bitrix_companies(self, api, companies_by_id, pulled_ids, config):

        domain = [("is_company", "=", True)]

        if pulled_ids:
            domain.append(("id", "not in", list(pulled_ids)))

        if config.last_sync:
            domain += ["|", ("bitrix_company_id", "=", False),
                       ("write_date", ">", config.last_sync)]
        candidates = self.search(domain)
        due_ids = config._due_retry_ids("res.partner", "crm.company")
        if due_ids:
            candidates |= self.search([
                ("is_company", "=", True), ("id", "in", due_ids)
            ])

        exported = 0
        errors = []

        for partner in candidates:
            if partner.id in pulled_ids:
                continue

            bitrix_id = partner.bitrix_company_id
            if bitrix_id and bitrix_id in companies_by_id:
                if self._company_to_odoo_sync(partner) == self._bitrix_to_odoo_company(
                    companies_by_id[bitrix_id]
                ):
                    continue
            payload = {"TITLE": partner.name or ""}

            if partner.phone:
                payload["PHONE"] = [
                    {"VALUE": partner.phone, "VALUE_TYPE": "WORK"}
                ]

            if partner.email:
                payload["EMAIL"] = [
                    {"VALUE": partner.email, "VALUE_TYPE": "WORK"}
                ]

            if not bitrix_id:
                originator = config._originator_id()
                origin_id = f"company_{partner.id}"
                payload.update({
                    "ORIGINATOR_ID": originator,
                    "ORIGIN_ID": origin_id,
                })

            operation = "crm.company.update" if bitrix_id else "crm.company.add"
            send = (
                (lambda: api.update_company(bitrix_id, payload))
                if bitrix_id else (
                    lambda: api.find_by_origin("company", originator, origin_id)
                    or api.create_company(payload)
                )
            )
            success, result, error = config._push_record(
                partner, operation, payload, send
            )
            if error:
                message = (
                    f"Empresa Odoo {partner.id} ({partner.name}), "
                    f"correo {partner.email or 'vacío'}: {error}"
                )
                _logger.warning("Bitrix24: %s", message)
                errors.append(message)
                continue
            if not success:
                continue

            if not bitrix_id:
                partner.bitrix_company_id = str(result)

            partner.bitrix_last_sync = fields.Datetime.now()
            exported += 1

        return exported, errors

    def sync_companies_with_bitrix(self, api, config):

        companies_cutoff = fields.Datetime.now()
        companies = api.get_companies(config._pull_filter(config.companies_cursor))
        companies_by_id = {
            str(company.get("ID")): company
            for company in companies if company.get("ID")
        }

        imported, updated, pulled_ids = (
            self._pull_bitrix_companies(companies)
        )
        config.companies_cursor = companies_cutoff

        exported, errors = self._push_bitrix_companies(
            api, companies_by_id, pulled_ids, config
        )

        return imported, updated, exported, errors
