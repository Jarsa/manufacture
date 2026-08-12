# Copyright 2017-18 ForgeFlow S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestMrpRequest(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.production_model = cls.env["mrp.production"]
        cls.request_model = cls.env["mrp.request"]
        cls.wiz_model = cls.env["mrp.request.create.mo"]
        cls.wiz_line_model = cls.env["mrp.request.create.mo.line"]
        cls.bom_model = cls.env["mrp.bom"]
        cls.boml_model = cls.env["mrp.bom.line"]
        cls.rule_model = cls.env["stock.rule"]
        cls.product_model = cls.env["product.product"]

        cls.company = cls.env.company
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.stock_loc = cls.env.ref("stock.stock_location_stock")
        cls.route_manuf = cls.env.ref("mrp.route_warehouse0_manufacture")
        cls.route_buy = cls.env.ref("purchase_stock.route_warehouse0_buy")
        # In 19.0 the warehouse Buy route is not product selectable by
        # default and `route_ids` reads are filtered by the field domain.
        cls.route_buy.product_selectable = True

        cls.component = cls.product_model.create(
            {"name": "Test component", "is_storable": True}
        )
        cls.product = cls.product_model.create(
            {
                "name": "Test Product",
                "is_storable": True,
                "mrp_request": True,
                "route_ids": [(6, 0, cls.route_manuf.ids)],
            }
        )
        cls.bom = cls._create_bom(cls.product)
        cls.product_no_bom = cls.product_model.create(
            {
                "name": "Test Product without BoM",
                "is_storable": True,
                "mrp_request": True,
                "route_ids": [(6, 0, cls.route_manuf.ids)],
            }
        )
        cls.product_orderpoint = cls.product_model.create(
            {
                "name": "Test Product for orderpoint",
                "is_storable": True,
                "mrp_request": True,
                "route_ids": [(6, 0, cls.route_manuf.ids)],
            }
        )
        cls._create_bom(cls.product_orderpoint)
        cls.product_route_buy = cls.product_model.create(
            {
                "name": "Test Product route buy",
                "is_storable": True,
                "route_ids": [(6, 0, cls.route_buy.ids)],
            }
        )
        cls._create_bom(cls.product_route_buy)

        cls.orderpoint = cls.env["stock.warehouse.orderpoint"].create(
            {
                "warehouse_id": cls.warehouse.id,
                "location_id": cls.warehouse.lot_stock_id.id,
                "product_id": cls.product_orderpoint.id,
                "product_min_qty": 10.0,
                "product_max_qty": 50.0,
            }
        )
        cls.test_user = cls.env["res.users"].create({"name": "John", "login": "test"})
        # Products/BoMs are created while the registry is loading (at_install):
        # make sure pending values reach the DB and the cache is consistent.
        cls.env.flush_all()
        cls.env.invalidate_all()

    @classmethod
    def _create_bom(cls, product):
        bom = cls.bom_model.create(
            {
                "product_id": product.id,
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_uom_id": product.uom_id.id,
                "product_qty": 1.0,
                "type": "normal",
            }
        )
        cls.boml_model.create(
            {
                "bom_id": bom.id,
                "product_id": cls.component.id,
                "product_qty": 1.0,
            }
        )
        return bom

    def procure(self, product, qty=4.0):
        values = {
            "date_planned": fields.Datetime.now(),
            "warehouse_id": self.warehouse,
        }
        self.rule_model.run(
            [
                self.rule_model.Procurement(
                    product,
                    qty,
                    product.uom_id,
                    self.stock_loc,
                    "TEST",
                    "TEST",
                    self.company,
                    values,
                )
            ]
        )
        return True

    def _get_request(self, product):
        return self.request_model.search([("product_id", "=", product.id)])

    def test_01_manufacture_request(self):
        """Tests manufacture request workflow."""
        self.procure(self.product)
        request = self._get_request(self.product)
        self.assertEqual(len(request), 1)
        self.assertEqual(request.state, "to_approve")
        self.assertEqual(request.origin, "TEST")
        request.button_draft()
        request.button_to_approve()
        request.button_approved()
        self.assertEqual(request.pending_qty, 4.0)
        wiz = self.wiz_model.with_context(
            active_ids=request.ids, active_model="mrp.request"
        ).create({})
        wiz.compute_product_line_ids()
        self.assertTrue(wiz.product_line_ids)
        self.assertEqual(wiz.product_line_ids.bottle_neck_factor, 0.0)
        wiz.mo_qty = 4.0
        wiz.create_mo()
        mo = self.production_model.search([("mrp_request_id", "=", request.id)])
        self.assertTrue(mo, "No MO created.")
        self.assertEqual(request.mrp_production_count, 1)
        self.assertEqual(request.pending_qty, 4.0)
        action = request.action_view_mrp_productions()
        self.assertEqual(action["res_id"], mo.id)
        request.button_done()
        self.assertEqual(request.state, "done")

    def test_02_assignation(self):
        """Tests assignation of manufacturing requests."""
        request = self.request_model.create(
            {
                "assigned_to": self.test_user.id,
                "product_id": self.product.id,
                "product_qty": 5.0,
                "bom_id": self.bom.id,
            }
        )
        self.assertNotEqual(request.name, "/")
        self.assertIn(
            self.test_user.partner_id, request.message_follower_ids.partner_id
        )
        self.bom.picking_type_id = self.warehouse.manu_type_id
        request._onchange_product_id()
        self.assertEqual(
            request.bom_id.product_tmpl_id,
            self.product.product_tmpl_id,
            "Wrong Bill of Materials.",
        )
        self.assertEqual(request.picking_type_id, self.warehouse.manu_type_id)
        request._onchange_picking_type_id()
        self.assertEqual(
            request.location_src_id,
            self.warehouse.manu_type_id.default_location_src_id,
        )
        request.write({"assigned_to": self.env.user.id})
        self.assertIn(self.env.user.partner_id, request.message_follower_ids.partner_id)
        request2 = request.copy()
        self.assertNotEqual(request2.name, request.name)
        # Multiple requests: the action opens the list view.
        request.mrp_production_ids = self.production_model.create(
            [
                {"product_id": self.product.id, "bom_id": self.bom.id},
                {"product_id": self.product.id, "bom_id": self.bom.id},
            ]
        )
        action = request.action_view_mrp_productions()
        self.assertIn(("id", "in", request.mrp_production_ids.ids), action["domain"])

    def test_03_substract_qty_from_orderpoint(self):
        """Quantity in Manufacturing Requests should be considered by
        orderpoints."""
        self.assertFalse(self._get_request(self.product_orderpoint))
        with mute_logger("odoo.addons.stock.models.stock_rule"):
            self.rule_model.run_scheduler()
        request = self._get_request(self.product_orderpoint)
        self.assertEqual(len(request), 1)
        self.assertEqual(request.orderpoint_id, self.orderpoint)
        qty_in_progress = self.orderpoint._quantity_in_progress()
        self.assertEqual(qty_in_progress[self.orderpoint.id], request.pending_qty)
        # Running again the scheduler should not generate a new MR.
        with mute_logger("odoo.addons.stock.models.stock_rule"):
            self.rule_model.run_scheduler()
        request = self._get_request(self.product_orderpoint)
        self.assertEqual(len(request), 1)

    def test_04_raise_errors(self):
        """Tests user errors raising properly."""
        with self.assertRaises(UserError):
            # No Bill of Materials:
            self.procure(self.product_no_bom)
        with self.assertRaises(UserError):
            # No Bill of Materials, direct call:
            self.route_manuf.rule_ids[0]._run_production_request(
                self.product_no_bom,
                1.0,
                self.product_no_bom.uom_id,
                self.stock_loc,
                "TEST",
                "TEST",
                self.company,
                {
                    "date_planned": fields.Datetime.now(),
                    "warehouse_id": self.warehouse,
                },
            )
        self.procure(self.product)
        request = self._get_request(self.product)
        request.button_approved()
        wiz = self.wiz_model.with_context(
            active_ids=request.ids, active_model="mrp.request"
        ).create({})
        wiz.compute_product_line_ids()
        wiz.mo_qty = 4.0
        wiz.create_mo()
        self.production_model.search(
            [("mrp_request_id", "=", request.id)]
        ).action_confirm()
        with self.assertRaises(UserError):
            # MOs not cancelled:
            request.button_draft()
        request.button_done()
        with self.assertRaises(UserError):
            # Done requests cannot be rejected:
            request.button_cancel()
        with self.assertRaises(UserError):
            # Wizard needs active_ids in context:
            self.wiz_model.create({})

    def test_04_bis_no_request_needed(self):
        """Products without the flag keep the standard manufacture flow."""
        product_plain = self.product_model.create(
            {
                "name": "Test Product plain MO",
                "is_storable": True,
                "route_ids": [(6, 0, self.route_manuf.ids)],
            }
        )
        self._create_bom(product_plain)
        self.procure(product_plain)
        self.assertFalse(self._get_request(product_plain))
        self.assertTrue(
            self.production_model.search([("product_id", "=", product_plain.id)])
        )

    def test_05_route_flag_buy(self):
        """A route flagged to generate MRs diverts buy procurements."""
        self.route_buy.mrp_request = True
        self.procure(self.product_route_buy)
        request = self._get_request(self.product_route_buy)
        self.assertEqual(len(request), 1)
        # The picking type falls back to the manufacturing operation type.
        self.assertEqual(request.picking_type_id, self.warehouse.manu_type_id)
        self.assertFalse(
            self.env["purchase.order.line"].search(
                [("product_id", "=", self.product_route_buy.id)]
            )
        )

    def test_06_mto_chain(self):
        """MRs created to fulfill a MO keep the link with the destination
        moves and propagate it to the created MOs."""
        bom_finished = self._create_bom(
            self.product_model.create({"name": "Test finished", "is_storable": True})
        )
        self.boml_model.create(
            {
                "bom_id": bom_finished.id,
                "product_id": self.product.id,
                "product_qty": 1.0,
            }
        )
        mo_parent = self.production_model.create(
            {
                "product_id": bom_finished.product_id.id,
                "bom_id": bom_finished.id,
                "product_qty": 2.0,
            }
        )
        mo_parent.action_confirm()
        move_dest = mo_parent.move_raw_ids.filtered(
            lambda m: m.product_id == self.product
        )
        rule = self.route_manuf.rule_ids[0]
        values = {
            "date_planned": fields.Datetime.now(),
            "warehouse_id": self.warehouse,
            "orderpoint_id": self.orderpoint,
            "move_dest_ids": move_dest,
        }
        rule._run_production_request(
            self.product,
            2.0,
            self.product.uom_id,
            self.stock_loc,
            "TEST/MTO",
            "TEST/MTO",
            self.company,
            values,
        )
        request = self._get_request(self.product)
        self.assertEqual(request.move_dest_ids, move_dest)
        request.button_approved()
        request.reference_ids = mo_parent.reference_ids
        wiz = self.wiz_model.with_context(
            active_ids=request.ids, active_model="mrp.request"
        ).create({})
        wiz.compute_product_line_ids()
        wiz.mo_qty = 2.0
        wiz.create_mo()
        mo = self.production_model.search([("mrp_request_id", "=", request.id)])
        finished_move = mo.move_finished_ids.filtered(
            lambda m: m.product_id == self.product
        )
        self.assertIn(move_dest, finished_move.move_dest_ids)
        self.assertFalse(finished_move.propagate_cancel)
        mo.action_cancel()
        request.button_cancel()
        self.assertEqual(request.state, "cancel")
        self.assertEqual(move_dest.state, "cancel")
        request.button_draft()
        self.assertEqual(request.state, "draft")

    def test_07_forecasted_report(self):
        """Confirmed MRs are reported as incoming quantity in the
        forecasted report."""
        self.procure(self.product)
        request = self._get_request(self.product)
        wh_location_ids = (
            self.env["stock.location"]
            .search([("id", "child_of", self.warehouse.view_location_id.id)])
            .ids
        )
        report = self.env["stock.forecasted_product_product"]
        res = report._get_report_header([], self.product.ids, wh_location_ids)
        self.assertEqual(
            res["product"][self.product.id]["mrp_request_qty"]["in"],
            request.pending_qty,
        )

    def test_08_forecast_graph(self):
        """Confirmed MRs are shown as forecasted receipts in the
        forecasted inventory graph."""
        self.procure(self.product)
        request = self._get_request(self.product)
        self.env.flush_all()
        report = self.env["report.stock.quantity"]
        rows_in = report.search(
            [("product_id", "=", self.product.id), ("state", "=", "in")]
        )
        self.assertEqual(sum(rows_in.mapped("product_qty")), request.pending_qty)
        rows_forecast = report.search(
            [
                ("product_id", "=", self.product.id),
                ("state", "=", "forecast"),
                ("date", "=", fields.Date.today()),
            ]
        )
        self.assertEqual(sum(rows_forecast.mapped("product_qty")), request.pending_qty)
        # Cancelled requests are not considered anymore.
        request.button_cancel()
        self.env.flush_all()
        self.assertFalse(
            report.search([("product_id", "=", self.product.id), ("state", "=", "in")])
        )

    def test_09_wizard_line_computes(self):
        """Wizard line computes handle zero quantities."""
        line = self.wiz_line_model.create(
            {
                "product_id": self.component.id,
                "product_qty": 0.0,
                "product_uom_id": self.component.uom_id.id,
                "location_id": self.stock_loc.id,
            }
        )
        self.assertEqual(line.bottle_neck_factor, 0.0)
        self.assertEqual(line.available_qty, 0.0)
