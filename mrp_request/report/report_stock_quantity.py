# Copyright 2025 Jarsa
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, tools


class ReportStockQuantity(models.Model):
    _inherit = "report.stock.quantity"

    def init(self):
        """Wrap the core SQL view to add the pending quantity of confirmed
        manufacturing requests as forecasted receipts, so they show up in
        the forecasted inventory graph."""
        res = super().init()
        # super() dropped any previous wrapper and re-created the plain view,
        # so the stale renamed view from a previous init can be dropped now.
        tools.drop_view_if_exists(self.env.cr, "report_stock_quantity_core")
        self.env.cr.execute(
            "ALTER VIEW report_stock_quantity RENAME TO report_stock_quantity_core"
        )
        report_period = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("stock.report_stock_quantity_period", default="3")
        )
        query = """
CREATE or REPLACE VIEW report_stock_quantity AS (
SELECT * FROM report_stock_quantity_core
UNION ALL
SELECT
    -mr.id - 1000000 AS id,
    mr.product_id,
    pp.product_tmpl_id,
    'in' AS state,
    COALESCE(mr.date_finished, mr.date_start)::date AS date,
    mr.pending_qty * uom_mr.factor / uom_pt.factor AS product_qty,
    mr.company_id,
    spt.warehouse_id
FROM mrp_request mr
JOIN product_product pp ON pp.id = mr.product_id
JOIN product_template pt ON pt.id = pp.product_tmpl_id
JOIN uom_uom uom_mr ON uom_mr.id = mr.product_uom_id
JOIN uom_uom uom_pt ON uom_pt.id = pt.uom_id
JOIN stock_picking_type spt ON spt.id = mr.picking_type_id
WHERE mr.state IN %(states)s
    AND pt.is_storable = true
    AND mr.pending_qty != 0
UNION ALL
SELECT
    -mr.id - 2000000 AS id,
    mr.product_id,
    pp.product_tmpl_id,
    'forecast' AS state,
    GENERATE_SERIES(
        GREATEST(
            COALESCE(mr.date_finished, mr.date_start)::date,
            (now() at time zone 'utc')::date
                - interval '%(report_period)s month'
        ),
        (now() at time zone 'utc')::date + interval '%(report_period)s month',
        '1 day'::interval
    )::date AS date,
    mr.pending_qty * uom_mr.factor / uom_pt.factor AS product_qty,
    mr.company_id,
    spt.warehouse_id
FROM mrp_request mr
JOIN product_product pp ON pp.id = mr.product_id
JOIN product_template pt ON pt.id = pp.product_tmpl_id
JOIN uom_uom uom_mr ON uom_mr.id = mr.product_uom_id
JOIN uom_uom uom_pt ON uom_pt.id = pt.uom_id
JOIN stock_picking_type spt ON spt.id = mr.picking_type_id
WHERE mr.state IN %(states)s
    AND pt.is_storable = true
    AND mr.pending_qty != 0
);
"""
        self.env.cr.execute(
            query,
            {
                "report_period": report_period,
                "states": tuple(self.env["mrp.request"]._get_incoming_states()),
            },
        )
        return res
