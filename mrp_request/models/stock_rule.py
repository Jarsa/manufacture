# Copyright 2018-20 ForgeFlow S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, models
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
            "product_description_variants",
            "propagate_cancel",
            "user_id",
        ]:
            data.pop(key)
        data["state"] = "to_approve"
        orderpoint = values.get("orderpoint_id")
        if orderpoint:
            data["orderpoint_id"] = orderpoint.id
        procurement_group = values.get("group_id")
        if procurement_group:
            data["procurement_group_id"] = procurement_group.id
        return data

    def _need_production_request(self, product_id, action="manufacture"):
        return action == "manufacture" and product_id.mrp_request

    def _run_production_request(
        self,
        product_id,
        product_qty,
        product_uom,
        location_id,
        name,
        origin,
        values,
        company_id,
    ):
        """Trying to handle this as much similar as possible to Odoo
        production orders. See `_run_manufacture` in Odoo standard."""
        request_obj = self.env["mrp.request"]
        request_obj_sudo = request_obj.sudo().with_company(values["company_id"].id)
        bom = self._get_matching_bom(product_id, company_id, values)
        if not bom:
            raise UserError(
                _(
                    "There is no Bill of Material found for the product %s. "
                    "Please define a Bill of Material for this product."
                )
                % (product_id.display_name,)
            )

        existing_request = self.env["mrp.request"].search(
             [
                ("product_id", "=", product_id.id),
                ("state", "in", ["draft","to_approve"]),
                ("product_uom_id", "=",product_uom.id),
                ("location_dest_id", "=",location_id.id),
                ("bom_id", "=",bom.id),
                ("company_id", "=", company_id.id),
            ]
        )
        if not existing_request:
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
        else:
            vals_to_update = {}

            vals_to_update['product_qty'] = product_qty

            current_origin = existing_request.origin or ""
            origins = current_origin.split(', ')

            if origin and origin not in origins:
                origins.append(origin)
                vals_to_update['origin'] = ", ".join(origins)

            existing_request.write(vals_to_update)
            request = existing_request

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
                subtype_xmlid='mail.mt_note',
            )
        if origin_production:
            request.message_post_with_source(
                "mail.message_origin_link",
                render_values={"self": request, "origin": origin_production},
                subtype_xmlid='mail.mt_note',
            )
        return True

    def _run_manufacture(self, procurements):
        no_mr_procs = []
        for procurement, _rule in procurements:
            if self._need_production_request(procurement.product_id):
                self._run_production_request(
                    procurement.product_id,
                    procurement.product_qty,
                    procurement.product_uom,
                    procurement.location_id,
                    procurement.name,
                    procurement.origin,
                    procurement.values,
                    procurement.company_id,
                )
            else:
                no_mr_procs.append((procurement, _rule))

        return super()._run_manufacture(no_mr_procs)
