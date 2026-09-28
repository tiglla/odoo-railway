from odoo import fields, models


class BitrixUserMapping(models.Model):
    _name = "bitrix.user.mapping"
    _description = "Vendedor Bitrix24 a responsable Odoo"
    _rec_name = "bitrix_user_id"

    config_id = fields.Many2one(
        "bitrix.config", required=True, ondelete="cascade", index=True
    )
    bitrix_user_id = fields.Char(string="ID vendedor Bitrix24", required=True)
    user_id = fields.Many2one("res.users", string="Responsable Odoo", required=True)

    _config_user_unique = models.Constraint(
        "UNIQUE(config_id, bitrix_user_id)",
        "Cada vendedor de Bitrix24 solo puede tener un responsable por configuración.",
    )
