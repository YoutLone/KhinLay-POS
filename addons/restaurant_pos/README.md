# Restaurant support for Odoo Point of Sale

An Odoo 19 Community integration for restaurant recipes, ingredient stock,
expenses, and reporting. **Odoo's built-in Point of Sale is the order-entry
app.** The separate custom Restaurant POS app is hidden. Keep this addon
installed to preserve historical custom orders and the recipe integration.

## Features

- Menu categories and items with list, form, and image kanban views.
- Odoo's built-in Restaurant register, floor plan, product catalog, payments,
  and receipts for new orders.
- Recipe-based ingredient deduction, low stock alerts, and consumption cost
  snapshots. Cancelling a paid order restores its ingredient quantities.
- Daily expenses with an item name, quantity, total MMK amount, calculated unit
  price, optional receipt, and seller ownership rules.
- Admin-only daily income and daily, weekly, and monthly profit and loss, PDF reports,
  graph and pivot views, and an OWL dashboard.
- Odoo Point of Sale register sales in those reports, with recipe ingredient
  deduction and refund restoration.

Open **Point of Sale > Restaurant** and choose **Open Register** or **Continue
Selling**. Select a floor and table, add products, and complete payment in the
standard POS. The existing Main Floor and Patio layouts and MMK currency are
used. The addon records recipe ingredient consumption when a POS sale is paid
and restores it for a refund. Products without a linked recipe still sell but
do not deduct ingredient stock.

For a GrabFood order entered manually, add its items in the POS as usual. On the
payment screen, tap **Source: In Store** to change it to **Source: GrabFood**
before validating the order. The saved order shows **GrabFood** under **Order
Source** in the Point of Sale order list and detail view; the order list also
has a GrabFood filter. Printed Financial Reports identify these sales as
GrabFood. Use the appropriate payment method for Grab's settlement rather than
recording customer cash that the restaurant did not receive. Record any Grab
commission as an expense to keep the cash profit figure accurate.

Restaurant Seller now grants the built-in POS User role; Restaurant Admin also
grants POS Administrator. Staff can use **Point of Sale > Restaurant
Operations** for ingredients and expenses. Managers can also manage product
links and recipes and view additional reports and legacy custom orders.
Built-in POS reports show POS orders. The addon's Daily Income and Profit and
Loss reports also retain historical custom orders.
Enter each purchased item as an expense row under **Point of Sale > Restaurant
Operations > Expenses**. For example, enter Eggs with quantity 10 and total
amount 1,000 MMK, then Dry noodles with quantity 1 and total amount 2,000 MMK.
The list allows adding rows directly. The **Daily Profit and Loss** report shows
sales income, all recorded expenses, and **Cash Profit / Loss = Income - Expenses**.
The weekly and monthly views sum those daily values. Recipe Cost is shown for
reference and is not subtracted again from cash profit. These figures track
cash paid and received, not accrual accounting or the value of unsold stock.
For correct day boundaries, set the company contact's timezone to Asia/Yangon;
when it is empty, reports use Asia/Yangon by default.
Managers can open **Point of Sale > Restaurant Operations > Sales Details**,
choose a start and end date, then open each matching POS order. **Print
Financial Report** uses the same date range to show POS and legacy sales,
including sold items and totals.
The built-in **Point of Sale > Reporting > Sales Details** dialog also accepts
first and last calendar days, displays matching sale lines as the dates change,
and includes every sale on those days in the printed report.

## Menu products and recipes

Each existing restaurant menu item has a linked service product in Odoo POS.
The linked product remains available in the Restaurant register. Its recipe
deducts ingredients at payment; a POS refund restores them and reverses their
cost. New products created directly in POS can be sold immediately. To track
their ingredient cost, link the product to a restaurant menu item and recipe.

### Menu choices at order time

Use Odoo's built-in product configurator for a choice such as fried rice with
egg or pork. No separate POS popup setup is needed:

1. Enable **Variants** under **Inventory > Configuration > Settings > Products**
   if **Attributes & Variants** is not visible on product forms. A POS manager
   can then create an attribute
   under **Point of Sale > Configuration > Products > Attributes**. Name it
   **Fried Rice Choice**, set **Display Type** to **Radio** or **Pills**, and set
   **Variant Creation** to **Never**. Add values such as **Egg** and **Pork**.
2. Create the base item under **Point of Sale > Restaurant Operations > Menu
   Product Links**. Set its name, category, and base price, then save. This
   creates its linked POS product automatically. You can also link an existing
   POS product in **POS Product** instead.
3. Open the linked product under **Point of Sale > Products > Products**. On
   **Attributes & Variants**, add **Fried Rice Choice** and its values. Use
   **Configure** on the attribute row to set any extra price for each value.
4. Start or refresh the Restaurant register. Tapping the product opens Odoo's
   choice popup before it is added to the order. The selected choice is saved
   on the order line. Keep the base price on the Menu Product Link; it syncs to
   the automatically created product.

Use **Radio** or **Pills** when the customer must choose one value. Use
**Multi-checkbox** with **Variant Creation: Never** for independent optional
extras. Attribute price extras change the sale price. The restaurant recipe
linked to the base menu item is the same for every choice; choice-specific
ingredient deduction would require additional recipe logic.

To use a product that already exists in the register, open its menu item under
**Point of Sale > Restaurant Operations > Menu Product Links** and choose it in
**POS Product**.
The automatically created product is removed from the register's available
products. The existing product keeps its name and price. Add a recipe to the
menu item before selling if you want ingredient cost in the profit report.
Existing paid register sales are included in income after upgrade; ingredient
deduction starts with new sales after the product is linked.

The Restaurant register shows product photos in its menu after a table is
selected. Upload a photo on the POS product or its Menu Product Link. Photos
uploaded on Menu Product Links are copied to the linked POS product. Sample
photos and their credits are in `static/img/menu/` and can be applied to
products without photos using `scripts/apply_sample_menu_images.py`.

## Requirements

- Odoo 19 Community on Python 3.11 or newer
- The Odoo `base`, `stock`, `point_of_sale`, and `pos_restaurant` modules, plus
  the included OCA `web_responsive` addon

## Installation

Add this repository's `addons` directory to Odoo's `addons_path`, update the
Apps list, then install **Restaurant POS** as the integration addon. Assign
users the Restaurant Seller or Restaurant Admin group. Install with demo data
enabled to get two categories
and five sample menu items. On a new installation, the main company uses MMK
(Myanmar kyat) as its currency. New menu items, orders, ingredients, expenses,
the standard POS register, and financial reports then use MMK by default.
If the company already has accounting entries or POS sales in another currency,
installation stops so those recorded amounts are not relabeled as kyat.
Updating an already installed module does not change the company currency;
see `DEPLOY.md` before changing a database with existing sales.

See the repository's `DEPLOY.md` for Docker Compose, Nginx, backup, restore,
and role setup instructions.

## Module layout

- `models/`: business models and their computations
- `views/`: backend views and menus
- `security/`: groups, record rules, and model access
- `wizards/`: transient workflows
- `reports/`: report models and templates
- `data/`: sample and configuration data
- `static/`: OWL dashboard assets and Apps listing assets
- `tests/`: Odoo transaction tests
