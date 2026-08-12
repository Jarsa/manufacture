# Copyright 2018-20 ForgeFlow S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models
from odoo.exceptions import UserError


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _prepare_mrp_request(
        self,
        product_id,
        product_qty,
        product_uom,
        location_id,
        name,
        origin,
        company_id,
        values,
        bom,
    ):
        data = self._prepare_mo_vals(
            product_id,
            product_qty,
            product_uom,
            location_id,
            name,
            origin,
            company_id,
            values,
            bom,
        )
        for key in [
            "date_deadline",
            "location_final_id",
            "never_product_template_attribute_value_ids",
            "product_description_variants",
            "propagate_cancel",
            "user_id",
        ]:
            data.pop(key, None)
        data["state"] = "to_approve"
        orderpoint = values.get("orderpoint_id")
        if orderpoint:
            data["orderpoint_id"] = orderpoint.id
        data["product_tmpl_id"] = product_id.product_tmpl_id.id
        picking_type = self.env["stock.picking.type"].browse(data["picking_type_id"])
        if picking_type.code != "mrp_operation":
            # Procurement diverted from a non-manufacture rule (e.g. buy):
            # fall back to the warehouse manufacturing operation type.
            warehouse = values.get("warehouse_id") or picking_type.warehouse_id
            manu_type = warehouse.manu_type_id
            data.update(
                picking_type_id=manu_type.id,
                location_src_id=manu_type.default_location_src_id.id,
                location_dest_id=manu_type.default_location_dest_id.id,
            )
        return data

    def _need_production_request(self, product_id):
        self.ensure_one()
        return self.action in ("manufacture", "buy") and (
            product_id.mrp_request or self.route_id.mrp_request
        )

    def _run_production_request(
        self,
        product_id,
        product_qty,
        product_uom,
        location_id,
        name,
        origin,
        company_id,
        values,
    ):
        """Trying to handle this as much similar as possible to Odoo
        production orders. See `_run_manufacture` in Odoo standard."""
        request_obj = self.env["mrp.request"]
        request_obj_sudo = request_obj.sudo().with_company(company_id.id)
        bom = self._get_matching_bom(product_id, company_id, values)
        if not bom:
            raise UserError(
                self.env._(
                    "There is no Bill of Material found for the product %s. "
                    "Please define a Bill of Material for this product.",
                    product_id.display_name,
                )
            )

        # create the MR as SUPERUSER because the current user may not
        # have the rights to do it (mto product launched by a sale for example)
        request = request_obj_sudo.create(
            self._prepare_mrp_request(
                product_id,
                product_qty,
                product_uom,
                location_id,
                name,
                origin,
                company_id,
                values,
                bom,
            )
        )
        origin_production = (
            values.get("move_dest_ids")
            and values["move_dest_ids"][0].raw_material_production_id
            or False
        )
        orderpoint = values.get("orderpoint_id")
        if orderpoint:
            request.message_post_with_source(
                "mail.message_origin_link",
                render_values={"self": request, "origin": orderpoint},
                subtype_xmlid="mail.mt_note",
            )
        if origin_production:
            request.message_post_with_source(
                "mail.message_origin_link",
                render_values={"self": request, "origin": origin_production},
                subtype_xmlid="mail.mt_note",
            )
        return True

    def _split_request_procurements(self, procurements):
        """Divert procurements that must generate a manufacturing request."""
        remaining_procs = []
        for procurement, rule in procurements:
            if rule._need_production_request(procurement.product_id):
                rule._run_production_request(*procurement)
            else:
                remaining_procs.append((procurement, rule))
        return remaining_procs

    @api.model
    def _run_manufacture(self, procurements):
        return super()._run_manufacture(self._split_request_procurements(procurements))

    def _run_buy(self, procurements):
        # `_run_buy` only exists (and is only dispatched) when
        # purchase_stock is installed.
        return super()._run_buy(self._split_request_procurements(procurements))
