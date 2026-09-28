import requests


class BitrixAPI:

    PAGE_SIZE = 50

    def __init__(self, webhook_url):
        self.webhook_url = webhook_url.rstrip("/") + "/"

    def call(self, method, params=None):

        url = self.webhook_url + method

        try:

            response = requests.post(
                url,
                json=params or {},
                timeout=30,
            )

        except requests.exceptions.RequestException as error:

            raise Exception(
                f"Bitrix24: no se pudo conectar "
                f"({error.__class__.__name__})."
            )

        try:

            data = response.json()

        except ValueError:

            data = None

        if data is None:

            raise Exception(
                f"Bitrix24: error HTTP "
                f"{response.status_code} "
                f"al llamar a {method}."
            )

        if "error" in data:

            raise Exception(
                f"Bitrix24: {data.get('error')} - "
                f"{data.get('error_description')}"
            )

        return data

    CONTACT_SELECT = [
        "ID",
        "NAME",
        "LAST_NAME",
        "SECOND_NAME",
        "PHONE",
        "EMAIL",
        "COMPANY_ID",
        "DATE_MODIFY",
    ]

    COMPANY_SELECT = [
        "ID",
        "TITLE",
        "COMPANY_TYPE",
        "PHONE",
        "EMAIL",
        "DATE_MODIFY",
    ]

    DEAL_SELECT = [
        "ID",
        "TITLE",
        "STAGE_ID",
        "STAGE_SEMANTIC_ID",
        "CATEGORY_ID",
        "CONTACT_ID",
        "COMPANY_ID",
        "OPPORTUNITY",
        "CURRENCY_ID",
        "ASSIGNED_BY_ID",
        "DATE_MODIFY",
    ]

    def _paginate(self, method, select, extra=None):

        results = []
        params = dict(
            extra or {},
            select=select,
            order={"ID": "ASC"},
        )
        start = 0

        while True:

            data = self.call(
                method,
                dict(params, start=start),
            )

            batch = data.get("result") or []

            results.extend(batch)

            if len(batch) < self.PAGE_SIZE:
                break

            start = data.get("next") or (
                start + self.PAGE_SIZE
            )

        return results

    def _add(self, method, values):

        return self.call(
            method,
            {"fields": values},
        ).get("result")

    def _update(self, method, bitrix_id, values):

        return self.call(
            method,
            {
                "id": bitrix_id,
                "fields": values,
            },
        )

    def find_by_origin(self, entity, originator_id, origin_id):
        if entity not in ("contact", "company", "deal"):
            raise ValueError("Entidad Bitrix24 no soportada.")
        records = self._paginate(
            f"crm.{entity}.list",
            ["ID"],
            {"filter": {
                "ORIGINATOR_ID": originator_id,
                "ORIGIN_ID": origin_id,
            }},
        )
        return records[0].get("ID") if records else False

    def test_connection(self):

        return self.call(
            "profile",
            {}
        )

    def get_contacts(self, extra=None):

        return self._paginate(
            "crm.contact.list",
            self.CONTACT_SELECT,
            extra,
        )

    def create_contact(self, values):

        return self._add("crm.contact.add", values)

    def update_contact(self, bitrix_id, values):

        return self._update(
            "crm.contact.update",
            bitrix_id,
            values,
        )

    def get_companies(self, extra=None):

        return self._paginate(
            "crm.company.list",
            self.COMPANY_SELECT,
            extra,
        )

    def create_company(self, values):

        return self._add("crm.company.add", values)

    def update_company(self, bitrix_id, values):

        return self._update(
            "crm.company.update",
            bitrix_id,
            values,
        )

    def get_deals(self, extra=None):

        return self._paginate(
            "crm.deal.list",
            self.DEAL_SELECT,
            extra,
        )

    def create_deal(self, values):

        return self._add("crm.deal.add", values)

    def update_deal(self, bitrix_id, values):

        return self._update("crm.deal.update", bitrix_id, values)

    def get_deal_userfields(self):

        return self._paginate(
            "crm.deal.userfield.list", ["ID", "FIELD_NAME", "USER_TYPE_ID"]
        )

    def create_deal_userfield(self, values):

        return self._add("crm.deal.userfield.add", values)

    def get_deal_categories(self):

        return self.call(
            "crm.dealcategory.list",
            {"select": ["ID", "NAME"]},
        ).get("result") or []

    def get_deal_stages(self, category_id=None):

        params = {
            "select": ["ID", "NAME", "SORT", "COLOR"],
            "filter": {
                "entity_type_id": "2",
            },
        }

        if category_id:
            params["filter"]["category_id"] = category_id

        return self.call("crm.status.list", params).get("result") or []
