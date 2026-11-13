"""Protect Restaurant POS orders when dining floors are archived."""

from odoo import models
from odoo.exceptions import UserError


class RestaurantFloor(models.Model):
    _inherit = "restaurant.floor"

    def write(self, vals):
        if vals.get("active") is False and any(
            table.current_restaurant_order_id for table in self.mapped("table_ids")
        ):
            raise UserError("Pay or cancel open table orders before archiving their floor.")
        return super().write(vals)
