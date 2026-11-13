"""Set initial restaurant company settings on a new installation."""

import base64

from odoo.exceptions import UserError
from odoo.tools import file_open


def set_sample_company_logo(env, overwrite=False):
    """Set the bundled logo, preserving a customized logo unless requested."""
    company = env.ref("base.main_company")
    if not overwrite and not company.uses_default_logo:
        return False
    with file_open("restaurant_pos/static/img/khin_lay_login.jpeg", "rb") as image:
        company.logo = base64.b64encode(image.read())
    return True


def enable_restaurant_pos_images(env):
    """Show product photos in restaurant registers."""
    env["pos.config"].search([
        ("module_pos_restaurant", "=", True),
    ]).write({"show_product_images": True})


def post_init_hook(env):
    company = env.ref("base.main_company")
    set_sample_company_logo(env)
    enable_restaurant_pos_images(env)
    mmk = env.ref("base.MMK")
    mmk.active = True
    if company.currency_id != mmk:
        # Changing the company currency after sales or accounting entries exist
        # would relabel their amounts rather than convert them.
        has_entries = env["account.move"].search_count([
            ("company_id", "=", company.id),
        ])
        has_sales = env["pos.order"].search_count([
            ("company_id", "=", company.id),
        ])
        if has_entries or has_sales:
            raise UserError(
                "Cannot make MMK the company currency automatically because this "
                "company already has accounting entries or POS sales. Review the "
                "existing amounts before changing its currency."
            )

        company.currency_id = mmk

    # Demo items are created before post-init hooks, so align their currency
    # with the company once the new database is configured.
    for xmlid in (
        "demo_menu_item_mohinga", "demo_menu_item_shan_noodles",
        "demo_menu_item_fried_rice", "demo_menu_item_milk_tea",
        "demo_menu_item_lime_juice",
    ):
        item = env.ref("restaurant_pos.%s" % xmlid, raise_if_not_found=False)
        if item:
            item.currency_id = mmk
