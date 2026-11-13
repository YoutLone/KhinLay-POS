"""Menu item and price snapshots on cash orders."""

from odoo import api, fields, models
from odoo.exceptions import UserError


class RestaurantOrderLine(models.Model):
    _name = "restaurant.order.line"
    _description = "Restaurant Order Line"
    _order = "id"

    order_id = fields.Many2one(
        "restaurant.order", required=True, index=True, ondelete="cascade"
    )
    menu_item_id = fields.Many2one(
        "restaurant.menu.item", required=True, ondelete="restrict"
    )
    qty = fields.Float(string="Quantity", required=True, default=1.0)
    unit_price = fields.Monetary(required=True, currency_field="currency_id")
    subtotal = fields.Monetary(
        compute="_compute_subtotal", store=True, currency_field="currency_id"
    )
    currency_id = fields.Many2one(
        "res.currency", related="order_id.currency_id", store=True, readonly=True
    )

    _quantity_positive = models.Constraint(
        "CHECK(qty > 0)", "Order line quantity must be greater than zero."
    )
    _unit_price_nonnegative = models.Constraint(
        "CHECK(unit_price >= 0)", "Order line price cannot be negative."
    )

    @api.depends("qty", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.unit_price

    @api.onchange("menu_item_id")
    def _onchange_menu_item_id(self):
        for line in self:
            line.unit_price = line.menu_item_id.price if line.menu_item_id else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        order_ids = [values.get("order_id") for values in vals_list if values.get("order_id")]
        self.env["restaurant.order"].browse(order_ids)._lock_for_update()
        prepared = []
        for values in vals_list:
            vals = dict(values)
            order = self.env["restaurant.order"].browse(vals.get("order_id"))
            item = self.env["restaurant.menu.item"].browse(vals.get("menu_item_id"))
            self._check_item(order, item)
            # The line keeps the current menu price after future menu edits.
            vals.pop("subtotal", None)
            vals.pop("currency_id", None)
            vals["unit_price"] = item.price
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if not vals:
            return True
        self.mapped("order_id")._lock_for_update()
        if any(line.order_id.state != "draft" for line in self):
            raise UserError("Paid and cancelled order lines cannot be edited.")
        if "order_id" in vals:
            raise UserError("Order lines cannot be moved between orders.")
        if set(vals) & {"subtotal", "currency_id"}:
            raise UserError("Order line prices are set from the menu item.")
        vals = dict(vals)
        if "menu_item_id" in vals:
            item = self.env["restaurant.menu.item"].browse(vals["menu_item_id"])
            for line in self:
                self._check_item(line.order_id, item)
            vals["unit_price"] = item.price
        elif "unit_price" in vals:
            raise UserError("Order line prices are set from the menu item.")
        return super().write(vals)

    def unlink(self):
        self.mapped("order_id")._lock_for_update()
        if any(line.order_id.state != "draft" for line in self):
            raise UserError("Paid and cancelled order lines cannot be deleted.")
        return super().unlink()

    @api.model
    def _check_item(self, order, item):
        if not order.exists() or order.state != "draft":
            raise UserError("Order lines can only be added to draft orders.")
        if not item.exists() or not item.active or not item.in_stock:
            raise UserError("Choose an available menu item.")
        if item.currency_id != order.currency_id:
            raise UserError("The menu item and order must use the same currency.")
