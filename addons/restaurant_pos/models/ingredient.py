"""Restaurant ingredient quantities and unit costs."""

from odoo import api, fields, models


class RestaurantIngredient(models.Model):
    _name = "restaurant.ingredient"
    _description = "Restaurant Ingredient"
    _order = "name"

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    unit_of_measure = fields.Selection(
        [
            ("unit", "Unit"),
            ("kg", "Kilogram"),
            ("g", "Gram"),
            ("l", "Liter"),
            ("ml", "Milliliter"),
        ],
        required=True,
        default="unit",
    )
    current_qty = fields.Float(string="Current Quantity", required=True, default=0.0)
    min_qty = fields.Float(string="Minimum Quantity", required=True, default=0.0)
    cost_per_unit = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    stock_value = fields.Monetary(
        compute="_compute_stock_value", store=True, currency_field="currency_id"
    )
    is_low_stock = fields.Boolean(compute="_compute_is_low_stock", store=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Ingredient names must be unique.")
    _current_qty_nonnegative = models.Constraint(
        "CHECK(current_qty >= 0)", "Ingredient quantity cannot be negative."
    )
    _min_qty_nonnegative = models.Constraint(
        "CHECK(min_qty >= 0)", "Minimum quantity cannot be negative."
    )
    _cost_nonnegative = models.Constraint(
        "CHECK(cost_per_unit >= 0)", "Ingredient unit cost cannot be negative."
    )

    @api.depends("current_qty", "cost_per_unit")
    def _compute_stock_value(self):
        for ingredient in self:
            ingredient.stock_value = ingredient.current_qty * ingredient.cost_per_unit

    @api.depends("current_qty", "min_qty")
    def _compute_is_low_stock(self):
        for ingredient in self:
            ingredient.is_low_stock = ingredient.current_qty < ingredient.min_qty

    def _lock_for_update(self):
        if self:
            self.env.cr.execute(
                "SELECT id FROM restaurant_ingredient WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                [self.ids],
            )
            self.invalidate_recordset(["current_qty", "cost_per_unit"])

    def write(self, vals):
        if set(vals) & {"current_qty", "cost_per_unit"}:
            self._lock_for_update()
        return super().write(vals)

    def unlink(self):
        self.check_access("unlink")
        ingredient_ids = self.ids
        recipes = self.env["restaurant.recipe"].search([
            ("ingredient_id", "in", ingredient_ids),
        ])
        historical_ids = set(self.env["restaurant.stock.move"].sudo().search([
            ("ingredient_id", "in", ingredient_ids),
        ]).mapped("ingredient_id").ids)
        historical_ids.update(self.env["restaurant.pos.consumption"].sudo().search([
            ("ingredient_id", "in", ingredient_ids),
        ]).mapped("ingredient_id").ids)

        recipes.unlink()
        historical = self.filtered(lambda ingredient: ingredient.id in historical_ids)
        if historical:
            historical.write({"active": False})
        deletable = self - historical
        if deletable:
            super(RestaurantIngredient, deletable).unlink()
        return True
