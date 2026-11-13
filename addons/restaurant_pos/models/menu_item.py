"""Sellable restaurant menu items."""

from odoo import api, fields, models
from odoo.fields import Command


class RestaurantMenuItem(models.Model):
    _name = "restaurant.menu.item"
    _description = "Restaurant Menu Item"
    _order = "name"

    name = fields.Char(required=True, index=True)
    category_id = fields.Many2one(
        "restaurant.menu.category",
        string="Category",
        required=True,
        index=True,
        ondelete="restrict",
    )
    price = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    image = fields.Image(max_width=1920, max_height=1920)
    description = fields.Text()
    active = fields.Boolean(default=True)
    in_stock = fields.Boolean(string="Available", default=True)
    pos_product_id = fields.Many2one(
        "product.product", string="POS Product", copy=False, ondelete="restrict",
        help="Choose an existing register product, or leave empty to create one automatically.",
    )
    pos_product_managed = fields.Boolean(copy=False, readonly=True)
    recipe_ids = fields.One2many("restaurant.recipe", "menu_item_id", string="Recipe")

    _price_nonnegative = models.Constraint(
        "CHECK(price >= 0)",
        "Menu item prices cannot be negative.",
    )
    _pos_product_unique = models.Constraint(
        "UNIQUE(pos_product_id)", "A POS product can belong to only one menu item."
    )

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        items._sync_pos_products()
        return items

    def write(self, vals):
        old_links = {
            item.id: (item.pos_product_id, item.pos_product_managed) for item in self
        } if "pos_product_id" in vals and not self.env.context.get(
            "skip_restaurant_pos_product_sync"
        ) else {}
        result = super().write(vals)
        if old_links:
            self.with_context(skip_restaurant_pos_product_sync=True).write({
                "pos_product_managed": False,
            })
            for item in self:
                old_product, managed = old_links[item.id]
                if managed and old_product and old_product != item.pos_product_id:
                    old_product.sudo().write({"available_in_pos": False})
        if not self.env.context.get("skip_restaurant_pos_product_sync") and set(vals) & {
            "name", "price", "active", "in_stock", "pos_product_id", "image",
        }:
            self._sync_pos_products(clear_image="image" in vals and not vals["image"])
        return result

    def _sync_pos_products(self, clear_image=False):
        """Keep one service product per menu item for the standard POS register."""
        Product = self.env["product.product"].sudo()
        PosCategory = self.env["pos.category"].sudo()
        Config = self.env["pos.config"].sudo()
        for item in self:
            category = PosCategory.search([("name", "=", item.category_id.name)], limit=1)
            if not category:
                category = PosCategory.create({"name": item.category_id.name})
            for config in Config.search([
                ("name", "=", "Restaurant"), ("limit_categories", "=", True),
            ]):
                if category not in config.iface_available_categ_ids:
                    config.write({
                        "iface_available_categ_ids": [Command.link(category.id)],
                    })
            values = {
                "name": item.name,
                "list_price": item.price,
                "available_in_pos": item.active and item.in_stock,
                "pos_categ_ids": [Command.set([category.id])],
            }
            image_values = {"image_1920": item.image} if item.image else (
                {"image_1920": False} if clear_image else {}
            )
            if item.pos_product_id:
                if item.pos_product_managed:
                    item.pos_product_id.sudo().write({**values, **image_values})
                else:
                    item.pos_product_id.sudo().write({
                        "available_in_pos": values["available_in_pos"],
                        "pos_categ_ids": [Command.link(category.id)],
                        **image_values,
                    })
            else:
                product = Product.create({**values, **image_values, "type": "service"})
                item.with_context(skip_restaurant_pos_product_sync=True).sudo().write({
                    "pos_product_id": product.id,
                    "pos_product_managed": True,
                })
