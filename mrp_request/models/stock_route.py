# Copyright 2025 Jarsa
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class StockRoute(models.Model):
    _inherit = "stock.route"

    mrp_request = fields.Boolean(
        string="Manufacturing Request",
        help="Check this box to generate a manufacturing request instead of "
        "a manufacturing or purchase order when a procurement is triggered "
        "through this route.",
    )
