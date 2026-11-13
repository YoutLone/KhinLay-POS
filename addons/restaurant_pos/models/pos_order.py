"""Apply restaurant recipes when a standard POS order is paid."""

from collections import defaultdict

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class PosOrder(models.Model):
    _inherit = "pos.order"

    restaurant_synced = fields.Boolean(default=False, copy=False, readonly=True)
    source = fields.Selection(
        selection_add=[("grabfood", "GrabFood")],
        ondelete={"grabfood": "set default"},
    )

    def action_pos_order_paid(self):
        result = super().action_pos_order_paid()
        if self:
            self.env.cr.execute(
                "SELECT id FROM pos_order WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                [self.ids],
            )
            self.invalidate_recordset(["restaurant_synced"])
        for order in self:
            if not order.restaurant_synced:
                order._sync_restaurant_ingredients()
                order.restaurant_synced = True
        return result

    def _sync_restaurant_ingredients(self):
        self.ensure_one()
        MenuItem = self.env["restaurant.menu.item"].sudo()
        Move = self.env["restaurant.pos.consumption"].sudo()
        items = MenuItem.search([
            ("pos_product_id", "in", self.lines.mapped("product_id").ids)
        ])
        items_by_product = {item.pos_product_id.id: item for item in items}
        demands = defaultdict(float)
        consumption = []
        refunds = []

        for line in self.lines:
            item = items_by_product.get(line.product_id.id)
            if line.qty > 0 and item:
                if not item.active or not item.in_stock:
                    raise UserError("The POS order contains an unavailable restaurant menu item.")
                for recipe in item.recipe_ids:
                    qty = line.qty * recipe.qty_per_item
                    demands[recipe.ingredient_id.id] += qty
                    consumption.append((line, recipe.ingredient_id, qty))
            elif line.qty < 0 and line.refunded_orderline_id:
                original = line.refunded_orderline_id
                original_moves = Move.search([("pos_line_id", "=", original.id)])
                for move in original_moves:
                    qty = -move.qty * (-line.qty / original.qty)
                    refunds.append((line, move.ingredient_id, qty, move.unit_cost))

        ingredients = self.env["restaurant.ingredient"].sudo().browse(
            sorted(set(demands) | {ingredient.id for _, ingredient, _, _ in refunds})
        )
        ingredients._lock_for_update()
        refunds_by_ingredient = defaultdict(float)
        for _, ingredient, qty, _ in refunds:
            refunds_by_ingredient[ingredient.id] += -qty
        for ingredient in ingredients:
            available = ingredient.current_qty + refunds_by_ingredient[ingredient.id]
            if float_compare(available, demands[ingredient.id], precision_digits=6) < 0:
                raise UserError("Insufficient stock for %s." % ingredient.name)

        moves = []
        for line, ingredient, qty in consumption:
            moves.append({
                "pos_order_id": self.id,
                "pos_line_id": line.id,
                "ingredient_id": ingredient.id,
                "qty": qty,
                "unit_cost": ingredient.cost_per_unit,
                "currency_id": ingredient.currency_id.id,
            })
        for line, ingredient, qty, unit_cost in refunds:
            moves.append({
                "pos_order_id": self.id,
                "pos_line_id": line.id,
                "ingredient_id": ingredient.id,
                "qty": qty,
                "unit_cost": unit_cost,
                "currency_id": ingredient.currency_id.id,
            })
        if moves:
            Move.create(moves)
            for ingredient in ingredients:
                ingredient.write({
                    "current_qty": ingredient.current_qty
                    + refunds_by_ingredient[ingredient.id] - demands[ingredient.id]
                })


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    restaurant_sale_date = fields.Datetime(
        string="Sale Date", related="order_id.date_order", readonly=True
    )
