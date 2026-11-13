"""Run with ``odoo shell`` once for an existing database.

The helper skips companies that already have a custom logo, so an uploaded
real logo is never replaced by this setup script.
"""

from odoo.addons.restaurant_pos.hooks import set_sample_company_logo

changed = set_sample_company_logo(env)
env.cr.commit()
print("Sample company logo applied." if changed else "Company logo already customized; no change.")
