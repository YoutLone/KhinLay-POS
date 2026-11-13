"""Create POS products for menu items that predate register integration."""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["restaurant.menu.item"].search([])._sync_pos_products()
