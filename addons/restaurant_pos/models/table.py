"""Use existing Odoo dining tables with custom Restaurant POS orders."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class RestaurantTable(models.Model):
    _inherit = "restaurant.table"

    restaurant_order_ids = fields.One2many("restaurant.order", "table_id")
    current_restaurant_order_id = fields.Many2one(
        "restaurant.order", compute="_compute_restaurant_order", string="Open Order"
    )
    restaurant_status = fields.Selection(
        [("available", "Available"), ("occupied", "Occupied")],
        compute="_compute_restaurant_order",
    )
    restaurant_currency_id = fields.Many2one(
        "res.currency", compute="_compute_restaurant_order"
    )
    restaurant_total = fields.Monetary(
        compute="_compute_restaurant_order", currency_field="restaurant_currency_id"
    )

    @api.depends(
        "restaurant_order_ids.state", "restaurant_order_ids.total_amount",
        "restaurant_order_ids.order_line_ids",
    )
    def _compute_restaurant_order(self):
        open_orders = self.env["restaurant.order"].search([
            ("table_id", "in", self.ids), ("state", "=", "draft")
        ], order="id desc")
        by_table = {}
        for order in open_orders:
            by_table.setdefault(order.table_id.id, order)
        for table in self:
            order = by_table.get(table.id)
            table.current_restaurant_order_id = order
            table.restaurant_status = (
                "occupied" if order and order.order_line_ids else "available"
            )
            table.restaurant_currency_id = (
                order.currency_id if order else self.env.company.currency_id
            )
            table.restaurant_total = order.total_amount if order else 0.0

    def _lock_restaurant_table_for_update(self):
        if self:
            self.env.cr.execute(
                "SELECT id FROM restaurant_table WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                [self.ids],
            )

    @api.model
    def get_restaurant_table_board(self):
        if not self.env.user.has_group("restaurant_pos.group_restaurant_seller"):
            raise AccessError("Only Restaurant POS staff can view dining tables.")
        floors = self.env["restaurant.floor"].search([
            ("active", "=", True)
        ])
        tables = self.search([
            ("floor_id", "in", floors.ids), ("active", "=", True)
        ])
        tables_by_floor = {floor.id: [] for floor in floors}
        for table in tables:
            tables_by_floor[table.floor_id.id].append({
                "id": table.id,
                "number": table.table_number,
                "seats": table.seats,
                "shape": table.shape,
                "x": table.position_h,
                "y": table.position_v,
                "width": table.width,
                "height": table.height,
                "status": table.restaurant_status,
                "total": table.restaurant_total,
                "order_name": table.current_restaurant_order_id.name or "",
            })
        return {
            "currency": self.env.company.currency_id.name,
            "floors": [{
                "id": floor.id,
                "name": floor.name,
                "background_color": floor.background_color or "",
                "tables": tables_by_floor[floor.id],
            } for floor in floors],
        }

    def action_open_restaurant_order(self):
        self.ensure_one()
        if not self.env.user.has_group("restaurant_pos.group_restaurant_seller"):
            raise AccessError("Only Restaurant POS staff can open table orders.")
        if not self.active:
            raise UserError("This table is archived.")
        self._lock_restaurant_table_for_update()
        Order = self.env["restaurant.order"]
        order = Order.search([
            ("table_id", "=", self.id), ("state", "=", "draft")
        ], limit=1)
        if not order:
            order = Order.create({"table_id": self.id})
        return {
            "type": "ir.actions.act_window",
            "name": "Table %s Order" % self.table_number,
            "res_model": "restaurant.order",
            "view_mode": "form",
            "view_id": self.env.ref("restaurant_pos.view_restaurant_order_form").id,
            "res_id": order.id,
            "target": "current",
        }

    def write(self, vals):
        if vals.get("active") is False and any(
            table.current_restaurant_order_id for table in self
        ):
            raise UserError("Pay or cancel the open order before archiving its table.")
        return super().write(vals)

    def unlink(self):
        if any(table.restaurant_order_ids for table in self):
            raise UserError("Archive a table that has order history instead of deleting it.")
        return super().unlink()
