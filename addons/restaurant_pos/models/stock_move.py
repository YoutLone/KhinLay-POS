"""Cost snapshots for ingredients consumed by paid orders."""

from odoo import api, fields, models


class RestaurantStockMove(models.Model):
    _name = "restaurant.stock.move"
    _description = "Restaurant Ingredient Consumption"
    _order = "id desc"

    order_id = fields.Many2one("restaurant.order", required=True, index=True, ondelete="cascade")
    order_line_id = fields.Many2one(
        "restaurant.order.line", required=True, index=True, ondelete="cascade"
    )
    ingredient_id = fields.Many2one(
        "restaurant.ingredient", required=True, index=True, ondelete="restrict"
    )
    qty = fields.Float(string="Consumed Quantity", required=True)
    unit_cost = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", required=True)
    total_cost = fields.Monetary(
        compute="_compute_total_cost", store=True, currency_field="currency_id"
    )
    company_cost = fields.Monetary(
        compute="_compute_company_cost", store=True, currency_field="company_currency_id"
    )
    company_currency_id = fields.Many2one(
        "res.currency", string="Company Currency",
        related="order_id.company_id.currency_id", store=True, readonly=True
    )
    reversed = fields.Boolean(default=False, readonly=True)

    _qty_positive = models.Constraint(
        "CHECK(qty > 0)", "Consumed quantity must be greater than zero."
    )
    _unit_cost_nonnegative = models.Constraint(
        "CHECK(unit_cost >= 0)", "Unit cost cannot be negative."
    )

    @api.depends("qty", "unit_cost")
    def _compute_total_cost(self):
        for move in self:
            move.total_cost = move.qty * move.unit_cost

    @api.depends("total_cost", "currency_id", "order_id.order_date", "order_id.company_id")
    def _compute_company_cost(self):
        for move in self:
            company = move.order_id.company_id
            date = fields.Date.to_date(move.order_id.order_date)
            move.company_cost = move.currency_id._convert(
                move.total_cost, company.currency_id, company, date
            ) if company and move.currency_id and date else 0.0
