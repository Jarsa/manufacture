# Copyright 2025 Jarsa
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    """Map the legacy procurement group of the requests to stock.reference.

    OpenUpgrade renames the ``procurement_group`` table to
    ``stock_reference`` keeping the record ids, so the legacy
    ``procurement_group_id`` column maps directly to the new
    ``reference_ids`` many2many.
    """
    if not openupgrade.column_exists(env.cr, "mrp_request", "procurement_group_id"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO mrp_request_stock_reference_rel
            (mrp_request_id, stock_reference_id)
        SELECT mr.id, mr.procurement_group_id
        FROM mrp_request mr
        JOIN stock_reference sr ON sr.id = mr.procurement_group_id
        ON CONFLICT DO NOTHING
        """,
    )
