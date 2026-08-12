# Copyright 2017 ForgeFlow S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class StockWarehouseOrderpoint(models.Model):
    _inherit = "stock.warehouse.orderpoint"

    def _quantity_in_progress(self):
        """Consider the pending quantity of open manufacturing requests as
        quantity in progress, so the replenishment does not propose it
        again."""
        res = super()._quantity_in_progress()
        request_groups = self.env["mrp.request"]._read_group(
            [
                ("orderpoint_id", "in", self.ids),
                ("state", "not in", ["done", "cancel"]),
            ],
            ["orderpoint_id", "product_uom_id"],
            ["pending_qty:sum"],
        )
        for orderpoint, uom, pending_qty_sum in request_groups:
            res[orderpoint.id] += uom._compute_quantity(
                pending_qty_sum, orderpoint.product_uom, round=False
            )
        return res
