# Copyright 2025 Jarsa Sistemas, S.A. de C.V.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from openupgradelib import openupgrade


fields_to_rename = [
    ("mrp.request", "mrp_request", "date_planned_start", "date_start"),
    ("mrp.request", "mrp_request", "date_planned_finished", "date_finished"),
]


@openupgrade.migrate()
def migrate(env, installed_version):
    openupgrade.rename_fields(env, fields_to_rename)
