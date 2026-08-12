# Copyright 2017 ForgeFlow S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.fields import Command


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    mrp_request_id = fields.Many2one(
        comodel_name="mrp.request",
        string="Manufacturing Request",
        copy=False,
        readonly=True,
    )

    def _create_update_move_finished(self):
        """`move_dest_ids` is a One2many field in mrp.production, thus we
        cannot indicate the same destination move in several MOs (which most
        probably would be the case with MRs).
        Storing them on the MR and writing them on the finished moves as it
        would happen if they were present in the MO, is the best workaround
        without changing the standard data model."""
        res = super()._create_update_move_finished()
        for production in self:
            request = production.mrp_request_id
            if request and request.move_dest_ids:
                production.move_finished_ids.filtered(
                    lambda m, production=production: m.product_id
                    == production.product_id
                ).write(
                    {
                        "move_dest_ids": [
                            Command.link(x.id) for x in request.move_dest_ids
                        ]
                    }
                )
        return res
