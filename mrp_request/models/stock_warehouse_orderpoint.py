# Copyright 2017 ForgeFlow S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class Orderpoint(models.Model):
    _inherit = "stock.warehouse.orderpoint"

    def _quantity_in_progress(self):
        res = super()._quantity_in_progress()
        for orderpoint in self.filtered(lambda x: x.id):
            mrp_requests = self.env['mrp.request'].search([
                ('orderpoint_id', '=', orderpoint.id),
                ('state', 'in', ['draft', 'confirmed'])
            ])
            for rec in mrp_requests:
                res[orderpoint.id] += rec.product_uom_id._compute_quantity(
                    rec.product_qty, orderpoint.product_uom
                )
        return res
