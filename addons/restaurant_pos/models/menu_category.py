"""Categories used to organize the restaurant menu."""

from odoo import fields, models


class RestaurantMenuCategory(models.Model):
    _name = "restaurant.menu.category"
    _description = "Restaurant Menu Category"
    _order = "name"

    name = fields.Char(required=True, index=True)

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "Menu category names must be unique.",
    )
