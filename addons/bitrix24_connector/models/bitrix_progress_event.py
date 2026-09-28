from odoo import fields, models


class BitrixProgressEvent(models.Model):
    _name = "bitrix.progress.event"
    _description = "Evento de avance pendiente para Bitrix24"
    _order = "id"

    project_id = fields.Many2one(
        "eigr.construction.project", required=True, ondelete="cascade", index=True,
    )
    event_key = fields.Char(required=True, readonly=True, index=True)
    comment = fields.Text(required=True, readonly=True)
    posted = fields.Boolean(readonly=True, default=False, index=True)

    _event_key_unique = models.Constraint(
        "UNIQUE(event_key)", "El evento de avance ya existe.",
    )

    def publish(self, api, config):
        errors = []
        for event in self.sudo().filtered(lambda item: not item.posted):
            project = event.project_id
            if not project.bitrix_deal_id:
                continue
            marker = f"[EIGR:{event.event_key}]"
            comment = f"{event.comment}\n{marker}"
            success, _result, error = config._push_record(
                event, "crm.timeline.comment.add", {"comment": comment},
                lambda: api.has_timeline_marker(project.bitrix_deal_id, marker)
                or api.add_timeline_comment(project.bitrix_deal_id, comment),
            )
            if error:
                errors.append(f"Obra {project.code}: {error}")
            elif success:
                event.posted = True
        return errors
