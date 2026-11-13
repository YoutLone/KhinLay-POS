"""Cash orders entered by restaurant sellers."""

from collections import defaultdict
import math

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare


class RestaurantOrder(models.Model):
    _name = "restaurant.order"
    _description = "Restaurant Order"
    _order = "order_date desc, id desc"

    name = fields.Char(
        string="Order Number", required=True, readonly=True, copy=False, default="New"
    )
    order_line_ids = fields.One2many(
        "restaurant.order.line", "order_id", string="Order Lines", copy=False
    )
    table_id = fields.Many2one(
        "restaurant.table", string="Table", index=True, copy=False, ondelete="restrict"
    )
    total_amount = fields.Monetary(
        compute="_compute_total_amount", store=True, currency_field="currency_id"
    )
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    company_currency_id = fields.Many2one(
        "res.currency", string="Company Currency",
        related="company_id.currency_id", store=True, readonly=True
    )
    company_amount = fields.Monetary(
        compute="_compute_company_amount", store=True, currency_field="company_currency_id"
    )
    payment_method = fields.Selection(
        [("cash", "Cash")], required=True, default="cash", readonly=True
    )
    state = fields.Selection(
        [("draft", "Draft"), ("paid", "Paid"), ("cancelled", "Cancelled")],
        required=True,
        default="draft",
        readonly=True,
    )
    seller_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, index=True
    )
    order_date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Order numbers must be unique.")
    _payment_method_cash = models.Constraint(
        "CHECK(payment_method = 'cash')", "Only cash payments are supported."
    )

    @api.depends("order_line_ids.subtotal")
    def _compute_total_amount(self):
        for order in self:
            order.total_amount = sum(order.order_line_ids.mapped("subtotal"))

    @api.depends("total_amount", "currency_id", "company_id", "order_date")
    def _compute_company_amount(self):
        for order in self:
            date = fields.Date.to_date(order.order_date)
            order.company_amount = order.currency_id._convert(
                order.total_amount, order.company_id.currency_id, order.company_id, date
            ) if order.company_id and order.currency_id and date else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        is_admin = self.env.user.has_group("restaurant_pos.group_restaurant_admin")
        prepared = []
        reserved_tables = set()
        for values in vals_list:
            vals = dict(values)
            if vals.get("state", "draft") != "draft":
                raise UserError("New orders must start in Draft state.")
            vals.pop("total_amount", None)
            order_number = self.env["ir.sequence"].next_by_code("restaurant.order")
            if not order_number:
                raise UserError("The restaurant order sequence is not configured.")
            vals["name"] = order_number
            vals["state"] = "draft"
            vals["payment_method"] = "cash"
            if not is_admin:
                vals["seller_id"] = self.env.user.id
                vals["order_date"] = fields.Datetime.now()
                vals["currency_id"] = self.env.company.currency_id.id
                vals["company_id"] = self.env.company.id
            if vals.get("table_id"):
                table = self.env["restaurant.table"].browse(vals["table_id"]).exists()
                if not table or not table.active:
                    raise UserError("Choose an available table.")
                table._lock_restaurant_table_for_update()
                if table.id in reserved_tables or self.search_count([
                    ("table_id", "=", table.id), ("state", "=", "draft")
                ]):
                    raise UserError("This table already has an open order.")
                reserved_tables.add(table.id)
            vals.pop("company_amount", None)
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if not vals:
            return True
        self._lock_for_update()
        is_admin = self.env.user.has_group("restaurant_pos.group_restaurant_admin")
        target_state = vals.get("state")
        paid_before = self.filtered(lambda order: order.state == "paid")
        if target_state:
            if set(vals) != {"state"}:
                raise UserError("Change the order state separately from its details.")
            if target_state == "paid":
                if any(order.state != "draft" for order in self):
                    raise UserError("Only draft orders can be paid.")
                self._check_can_pay()
            elif target_state == "cancelled":
                if not is_admin:
                    raise AccessError("Only Restaurant Admin can cancel orders.")
                if any(order.state not in ("draft", "paid") for order in self):
                    raise UserError("This order is already cancelled.")
            else:
                raise UserError("Use the Pay or Cancel action to change order state.")
        else:
            if any(order.state != "draft" for order in self):
                raise UserError("Paid and cancelled orders cannot be edited.")
            if set(vals) & {
                "name", "total_amount", "company_amount", "company_currency_id",
                "payment_method", "table_id",
            }:
                raise UserError("Order number, total, and payment method are managed automatically.")
            if not is_admin and set(vals) - {"order_line_ids"}:
                raise AccessError("Sellers may only edit draft order lines.")
            if set(vals) & {"currency_id", "company_id"} and any(
                order.order_line_ids for order in self
            ):
                raise UserError("Remove order lines before changing the currency or company.")
        result = super().write(vals)
        if target_state == "paid":
            self._consume_ingredients()
        elif target_state == "cancelled":
            paid_before._restore_ingredients()
        return result

    def _lock_for_update(self):
        """Serialize state changes with order line edits in this transaction."""
        if self:
            self.env.cr.execute(
                "SELECT id FROM restaurant_order WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                [self.ids],
            )
            self.invalidate_recordset(["state", "order_line_ids"])

    def _check_can_pay(self):
        for order in self:
            if not order.order_line_ids:
                raise UserError("Add at least one menu item before payment.")
            for line in order.order_line_ids:
                if not line.menu_item_id.active or not line.menu_item_id.in_stock:
                    raise UserError("An order line contains an unavailable menu item.")

    def _consume_ingredients(self):
        """Deduct recipe quantities and snapshot ingredient cost at payment."""
        lines = self.mapped("order_line_ids")
        recipes = self.env["restaurant.recipe"].sudo().search([
            ("menu_item_id", "in", lines.mapped("menu_item_id").ids)
        ])
        by_menu = defaultdict(list)
        for recipe in recipes:
            by_menu[recipe.menu_item_id.id].append(recipe)

        demands = defaultdict(float)
        consumptions = []
        for line in lines:
            for recipe in by_menu[line.menu_item_id.id]:
                qty = line.qty * recipe.qty_per_item
                demands[recipe.ingredient_id.id] += qty
                consumptions.append((line, recipe.ingredient_id.id, qty))

        ingredients = self.env["restaurant.ingredient"].sudo().browse(sorted(demands))
        ingredients._lock_for_update()
        for ingredient in ingredients:
            needed = demands[ingredient.id]
            if float_compare(ingredient.current_qty, needed, precision_digits=6) < 0:
                raise UserError("Insufficient stock for %s." % ingredient.name)

        move_vals = []
        ingredient_by_id = {ingredient.id: ingredient for ingredient in ingredients}
        for line, ingredient_id, qty in consumptions:
            ingredient = ingredient_by_id[ingredient_id]
            move_vals.append({
                "order_id": line.order_id.id,
                "order_line_id": line.id,
                "ingredient_id": ingredient_id,
                "qty": qty,
                "unit_cost": ingredient.cost_per_unit,
                "currency_id": ingredient.currency_id.id,
            })
        if move_vals:
            self.env["restaurant.stock.move"].sudo().create(move_vals)
            for ingredient in ingredients:
                ingredient.write({
                    "current_qty": max(0.0, ingredient.current_qty - demands[ingredient.id])
                })

    def _restore_ingredients(self):
        """Return stock when an admin cancels a previously paid order."""
        moves = self.env["restaurant.stock.move"].sudo().search([
            ("order_id", "in", self.ids), ("reversed", "=", False)
        ])
        demands = defaultdict(float)
        for move in moves:
            demands[move.ingredient_id.id] += move.qty
        ingredients = self.env["restaurant.ingredient"].sudo().browse(sorted(demands))
        ingredients._lock_for_update()
        for ingredient in ingredients:
            ingredient.write({"current_qty": ingredient.current_qty + demands[ingredient.id]})
        moves.write({"reversed": True})

    def action_pay(self):
        self.write({"state": "paid"})
        return True

    def _check_table_screen_access(self):
        self.ensure_one()
        if not self.env.user.has_group("restaurant_pos.group_restaurant_seller"):
            raise AccessError("Only Restaurant POS staff can use table orders.")
        if not self.table_id:
            raise UserError("This order is not assigned to a table.")
        if self.state != "draft":
            raise UserError("This table order is no longer open. Return to Tables to start a new order.")

    def _table_order_summary(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "table_number": self.table_id.table_number,
            "floor_name": self.table_id.floor_id.name,
            "currency": self.currency_id.name,
            "total": self.total_amount,
            "lines": [{
                "id": line.id,
                "menu_item_id": line.menu_item_id.id,
                "name": line.menu_item_id.name,
                "qty": line.qty,
                "unit_price": line.unit_price,
                "subtotal": line.subtotal,
            } for line in self.order_line_ids],
        }

    def get_table_order_screen(self):
        """Catalog and current cart for the Restaurant POS table screen."""
        self._check_table_screen_access()
        items = self.env["restaurant.menu.item"].search([
            ("active", "=", True),
            ("in_stock", "=", True),
            ("currency_id", "=", self.currency_id.id),
        ])
        categories = items.mapped("category_id").sorted("name")
        return {
            "order": self._table_order_summary(),
            "categories": [{"id": category.id, "name": category.name} for category in categories],
            "items": [{
                "id": item.id,
                "name": item.name,
                "category_id": item.category_id.id,
                "price": item.price,
                "description": item.description or "",
                "has_image": bool(item.image),
            } for item in items],
        }

    def add_table_menu_item(self, menu_item_id):
        """Add a menu item immediately so returning to the table keeps the cart."""
        self._check_table_screen_access()
        self._lock_for_update()
        item = self.env["restaurant.menu.item"].browse(menu_item_id).exists()
        Line = self.env["restaurant.order.line"]
        Line._check_item(self, item)
        existing = self.order_line_ids.filtered(
            lambda line: line.menu_item_id == item and float_compare(
                line.unit_price, item.price, precision_rounding=self.currency_id.rounding
            ) == 0
        )[:1]
        if existing:
            existing.write({"qty": existing.qty + 1})
        else:
            Line.create({"order_id": self.id, "menu_item_id": item.id, "qty": 1})
        return self._table_order_summary()

    def set_table_line_quantity(self, line_id, quantity):
        self._check_table_screen_access()
        self._lock_for_update()
        line = self.order_line_ids.filtered(lambda candidate: candidate.id == line_id)
        if not line:
            raise UserError("This item is no longer in the table order.")
        try:
            qty = float(quantity)
        except (TypeError, ValueError):
            raise UserError("Enter a valid quantity.") from None
        if not math.isfinite(qty) or qty < 0:
            raise UserError("Enter a valid quantity.")
        if qty == 0:
            # Seller ACLs prohibit general line deletion; this checked table
            # action may remove a line only from its own draft order.
            line.sudo().unlink()
        else:
            line.write({"qty": qty})
        return self._table_order_summary()

    def pay_table_order(self, cash_received):
        """Check the live total before recording a cash payment."""
        self._check_table_screen_access()
        self._lock_for_update()
        try:
            received = float(cash_received)
        except (TypeError, ValueError):
            raise UserError("Enter the cash received.") from None
        if not math.isfinite(received) or float_compare(
            received, self.total_amount, precision_rounding=self.currency_id.rounding
        ) < 0:
            raise UserError("Cash received must cover the current order total.")
        summary = self._table_order_summary()
        self.action_pay()
        return {
            "order": summary,
            "cash_received": received,
            "change": self.currency_id.round(received - summary["total"]),
        }

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True
