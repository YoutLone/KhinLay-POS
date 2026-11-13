"""Ingredient quantities consumed by one menu item."""

from odoo import fields, models


class RestaurantRecipe(models.Model):
    _name = "restaurant.recipe"
    _description = "Restaurant Recipe Ingredient"
    _order = "menu_item_id, ingredient_id"

    menu_item_id = fields.Many2one(
        "restaurant.menu.item", required=True, index=True, ondelete="cascade"
    )
    ingredient_id = fields.Many2one(
        "restaurant.ingredient", required=True, index=True, ondelete="restrict"
    )
    qty_per_item = fields.Float(string="Quantity per Item", required=True)
    unit_of_measure = fields.Selection(related="ingredient_id.unit_of_measure", readonly=True)

    _menu_ingredient_unique = models.Constraint(
        "UNIQUE(menu_item_id, ingredient_id)",
        "Each ingredient can appear only once in a menu item's recipe.",
    )
    _qty_positive = models.Constraint(
        "CHECK(qty_per_item > 0)", "Recipe quantity must be greater than zero."
    )
