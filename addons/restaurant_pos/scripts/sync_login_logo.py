"""Run with ``odoo shell`` to replace the main company's logo with the addon PNG.

This intentionally replaces the existing company logo. Use it after changing
``static/img/sample_login_logo.png`` in an existing database.
"""

from odoo.addons.restaurant_pos.hooks import set_sample_company_logo

set_sample_company_logo(env, overwrite=True)
env.cr.commit()
print("Company logo updated from restaurant_pos/static/img/khin_lay_login.jpeg.")
