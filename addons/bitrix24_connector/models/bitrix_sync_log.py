from odoo import models, fields, api

class BitrixSyncLog(models.Model):

    _name = "bitrix.sync.log"
    _description = "Registro de sincronización Bitrix24"
    _order = "run_datetime desc, id desc"

    name = fields.Char(
        string="Referencia",
        compute="_compute_name",
    )

    config_id = fields.Many2one(
        "bitrix.config",
        string="Configuración",
        ondelete="cascade",
    )

    run_datetime = fields.Datetime(
        string="Fecha de ejecución",
        readonly=True,
        default=fields.Datetime.now,
    )

    direction = fields.Selection(
        [
            ("pull", "Bitrix24 → Odoo"),
            ("push", "Odoo → Bitrix24"),
            ("both", "Bidireccional"),
        ],
        string="Dirección",
        readonly=True,
    )

    incremental = fields.Boolean(
        string="Incremental",
        readonly=True,
    )

    imported = fields.Integer(string="Importados", readonly=True)

    updated = fields.Integer(string="Actualizados", readonly=True)

    exported = fields.Integer(string="Exportados", readonly=True)

    failed = fields.Integer(string="Fallidos", readonly=True)

    error_log = fields.Text(string="Errores", readonly=True)

    resource_model = fields.Char(string="Modelo Odoo", readonly=True, index=True)
    resource_id = fields.Integer(string="ID Odoo", readonly=True, index=True)
    operation = fields.Char(string="Operación Bitrix24", readonly=True)
    payload_json = fields.Text(string="Datos enviados", readonly=True)
    status = fields.Selection(
        [
            ("success", "Enviado"),
            ("failed", "Fallido"),
            ("retried", "Reintentado"),
            ("discarded", "Registro eliminado"),
        ],
        string="Estado",
        readonly=True,
        index=True,
    )
    attempts = fields.Integer(string="Intentos", readonly=True)
    next_retry = fields.Datetime(string="Próximo reintento", readonly=True)

    @api.model
    def discard_missing_retries(self, config):
        logs = self.sudo().search([
            ("config_id", "=", config.id),
            ("status", "=", "failed"),
            ("next_retry", "<=", fields.Datetime.now()),
        ])
        for log in logs:
            try:
                exists = self.env[log.resource_model].sudo().browse(
                    log.resource_id
                ).exists()
            except KeyError:
                exists = False
            if not exists:
                log.write({"status": "discarded"})

    @api.depends("direction", "run_datetime")
    def _compute_name(self):

        labels = dict(self._fields["direction"].selection)

        for log in self:

            log.name = "%s - %s" % (
                labels.get(log.direction, ""),
                log.run_datetime or "",
            )
