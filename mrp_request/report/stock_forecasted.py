# Copyright 2025 Jarsa
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from collections import defaultdict

from odoo import models


class StockForecastedProductProduct(models.AbstractModel):
    _inherit = "stock.forecasted_product_product"

    def _get_report_header(self, product_template_ids, product_ids, wh_location_ids):
        """Add the pending quantity of confirmed manufacturing requests as
        incoming quantity in the forecasted report."""
        res = super()._get_report_header(
            product_template_ids, product_ids, wh_location_ids
        )
        domain = self._product_domain(product_template_ids, product_ids)
        domain += [
            ("state", "in", self.env["mrp.request"]._get_incoming_states()),
            ("location_dest_id", "in", wh_location_ids),
        ]
        qty_in = defaultdict(float)
        for product, uom, pending_qty_sum in self.env["mrp.request"]._read_group(
            domain,
            ["product_id", "product_uom_id"],
            ["pending_qty:sum"],
        ):
            qty_in[product.id] += uom._compute_quantity(
                pending_qty_sum, product.uom_id, round=False
            )
        self._add_product_quantities(
            res, product_template_ids, product_ids, "mrp_request_qty", qty_in, {}
        )
        return res
