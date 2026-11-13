"""Signed ingredient and cost snapshots for standard POS sales and refunds."""

from odoo import api, fields, models


class RestaurantPosConsumption(models.Model):
    _name = "restaurant.pos.consumption"
    _description = "POS Ingredient Consumption"
    _order = "id desc"

    pos_order_id = fields.Many2one("pos.order", required=True, index=True, ondelete="cascade")
    pos_line_id = fields.Many2one("pos.order.line", required=True, index=True, ondelete="cascade")
    ingredient_id = fields.Many2one("restaurant.ingredient", required=True, ondelete="restrict")
    qty = fields.Float(string="Quantity Change", required=True)
    unit_cost = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", required=True)
    total_cost = fields.Monetary(compute="_compute_total_cost", store=True, currency_field="currency_id")
    company_id = fields.Many2one("res.company", related="pos_order_id.company_id", store=True)
    company_currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
    company_cost = fields.Monetary(
        compute="_compute_company_cost", store=True, currency_field="company_currency_id"
    )

    _line_ingredient_unique = models.Constraint(
        "UNIQUE(pos_line_id, ingredient_id)",
        "An ingredient can be recorded only once per POS line.",
    )

    @api.depends("qty", "unit_cost")
    def _compute_total_cost(self):
        for move in self:
            move.total_cost = move.qty * move.unit_cost

    @api.depends("total_cost", "currency_id", "pos_order_id.date_order", "company_id")
    def _compute_company_cost(self):
        for move in self:
            company = move.company_id
            date = fields.Date.to_date(move.pos_order_id.date_order)
            move.company_cost = move.currency_id._convert(
                move.total_cost, company.currency_id, company, date
            ) if company and move.currency_id and date else 0.0
