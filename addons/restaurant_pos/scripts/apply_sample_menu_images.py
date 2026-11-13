"""Run with ``odoo shell`` to fill missing POS product photos once.

Existing product images are preserved. Linked Menu Product Links receive the
same photo, so their image stays in sync with the POS product.
"""

import base64

from odoo.tools import file_open


sample_images = {
    "Egg": "egg.jpg",
    "Hta Min Thoke": "rice_salad.jpg",
    "Hta Min Thoke (Egg)": "rice_salad.jpg",
    "Mohinga": "mohinga.jpg",
    "Toe Phu Thoke": "toe_phu_thoke.jpg",
}

updated = []
for name, filename in sample_images.items():
    with file_open(f"restaurant_pos/static/img/menu/{filename}", "rb") as image:
        content = base64.b64encode(image.read())
    for product in env["product.product"].search([
        ("name", "=", name), ("available_in_pos", "=", True),
    ]):
        if product.image_1920:
            continue
        item = env["restaurant.menu.item"].search([
            ("pos_product_id", "=", product.id),
        ], limit=1)
        if item and item.image:
            item._sync_pos_products()
        elif item:
            item.image = content
        else:
            product.image_1920 = content
        updated.append(name)

env.cr.commit()
print("Added sample photos:", ", ".join(updated) if updated else "none needed")
