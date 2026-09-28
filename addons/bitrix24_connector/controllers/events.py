import hmac
import logging

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class BitrixDealEvents(http.Controller):
    @http.route(
        "/bitrix24/events/deal", type="http", auth="public", methods=["POST"],
        csrf=False, save_session=False,
    )
    def deal_event(self, **_kwargs):
        form = request.httprequest.form
        event = (form.get("event") or "").upper()
        deal_id = form.get("data[FIELDS][ID]")
        member_id = form.get("auth[member_id]") or ""
        token = form.get("auth[application_token]") or ""
        if event not in ("ONCRMDEALADD", "ONCRMDEALUPDATE"):
            return request.make_response("unsupported event", status=400)
        if not deal_id or not deal_id.isdecimal() or not member_id or not token:
            return request.make_response("invalid event", status=400)
        configs = request.env["bitrix.config"].sudo().search([
            ("active", "=", True), ("event_member_id", "=", member_id),
        ])
        config = configs.filtered(lambda item: item.event_application_token and hmac.compare_digest(
            item.event_application_token, token,
        ))[:1]
        if not config:
            return request.make_response("forbidden", status=403)
        try:
            request.env["bitrix.deal"].sudo().sync_deal_event(config, deal_id)
        except Exception:
            _logger.exception("Bitrix24: falló el evento del negocio %s", deal_id)
            return request.make_response("retry later", status=503)
        return request.make_response("ok", status=200)
