from odoo import fields, models


class EigrConstructionProjectBitrixLink(models.Model):
    _inherit = "eigr.construction.project"

    bitrix_deal_id = fields.Char(
        string="ID del negocio Bitrix24",
        index=True,
        copy=False,
        readonly=True,
    )

    _bitrix_deal_id_unique = models.Constraint(
        "UNIQUE(bitrix_deal_id)",
        "El negocio de Bitrix24 ya tiene una obra vinculada.",
    )
