"""Display restaurant product images after upgrading existing databases."""

from odoo import SUPERUSER_ID, api
from odoo.addons.restaurant_pos.hooks import enable_restaurant_pos_images


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    enable_restaurant_pos_images(env)
    env["restaurant.menu.item"].search([])._sync_pos_products()
