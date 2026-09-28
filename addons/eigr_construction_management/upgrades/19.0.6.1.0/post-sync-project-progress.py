from odoo import SUPERUSER_ID, api
from odoo.tools.float_utils import float_compare


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    projects = env["eigr.construction.project"].with_context(
        active_test=False
    ).search([("valuation_ids.state", "=", "approved")])
    for project in projects:
        latest = project.latest_valuation_id
        if latest and float_compare(
            project.progress_percent, latest.actual_progress, precision_digits=3
        ) != 0:
            project.write({"progress_percent": latest.actual_progress})
