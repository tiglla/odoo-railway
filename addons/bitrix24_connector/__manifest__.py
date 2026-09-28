{
    "name": "Bitrix24 Connector",
    "version": "19.0.4.1.0",
    "category": "CRM",
    "summary": "Integración directa Odoo 19 con Bitrix24",
    "author": "Custom",
    "license": "LGPL-3",

    "depends": [
        "base",
        "contacts",
        "eigr_construction_management",
    ],

    "data": [
    "security/ir.model.access.csv",
    "data/bitrix_cron.xml",
    "views/bitrix_config_views.xml",
    "views/res_partner_views.xml",
    "views/bitrix_field_mapping_views.xml",
    "views/bitrix_deal_views.xml",
    "views/construction_project_link_views.xml",
    "views/bitrix_sync_log_views.xml",
],

    "external_dependencies": {
        "python": [
            "requests",
        ],
    },

    "installable": True,
    "application": True,
}
