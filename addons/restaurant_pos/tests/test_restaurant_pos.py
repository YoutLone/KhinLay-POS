"""Core sale, stock, reporting, and role permissions."""

import base64
from datetime import datetime, time, timedelta
from io import BytesIO

from PIL import Image

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import Form
from odoo.tests.common import TransactionCase


class TestRestaurantPOS(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        seller_group = cls.env.ref("restaurant_pos.group_restaurant_seller")
        admin_group = cls.env.ref("restaurant_pos.group_restaurant_admin")
        internal_group = cls.env.ref("base.group_user")
        cls.seller = cls.env["res.users"].create({
            "name": "Restaurant Test Seller",
            "login": "restaurant_test_seller",
            "group_ids": [(6, 0, [internal_group.id, seller_group.id])],
        })
        cls.admin = cls.env["res.users"].create({
            "name": "Restaurant Test Admin",
            "login": "restaurant_test_admin",
            "group_ids": [(6, 0, [internal_group.id, admin_group.id])],
        })
        cls.env.company.partner_id.tz = "Asia/Yangon"
        cls.category = cls.env["restaurant.menu.category"].create({"name": "Test Meals"})
        cls.item = cls.env["restaurant.menu.item"].create({
            "name": "Test Noodles",
            "category_id": cls.category.id,
            "price": 20.0,
        })
        cls.ingredient = cls.env["restaurant.ingredient"].create({
            "name": "Test Flour",
            "unit_of_measure": "kg",
            "current_qty": 10.0,
            "min_qty": 3.0,
            "cost_per_unit": 3.0,
        })
        cls.env["restaurant.recipe"].create({
            "menu_item_id": cls.item.id,
            "ingredient_id": cls.ingredient.id,
            "qty_per_item": 2.0,
        })

    def _make_order(self, qty=2.0):
        return self.env["restaurant.order"].with_user(self.seller).create({
            "order_line_ids": [(0, 0, {"menu_item_id": self.item.id, "qty": qty})],
        })

    def _make_pos_order(self, session, qty=1.0, refunded_line=None):
        amount = qty * self.item.pos_product_id.list_price
        line = {
            "name": "Restaurant test line",
            "product_id": self.item.pos_product_id.id,
            "qty": qty,
            "price_unit": self.item.pos_product_id.list_price,
            "price_subtotal": amount,
            "price_subtotal_incl": amount,
        }
        if refunded_line:
            line["refunded_orderline_id"] = refunded_line.id
        return self.env["pos.order"].create({
            "session_id": session.id,
            "is_refund": qty < 0,
            "amount_total": amount,
            "amount_tax": 0,
            "amount_paid": amount,
            "amount_return": 0,
            "lines": [(0, 0, line)],
        })

    def test_order_total_and_price_snapshot(self):
        order = self._make_order()
        self.assertEqual(order.total_amount, 40.0)
        self.item.price = 25.0
        self.assertEqual(order.order_line_ids.unit_price, 20.0)
        self.assertEqual(order.total_amount, 40.0)
        self.assertEqual(self.item.pos_product_id.list_price, 25.0)

    def test_form_creates_and_pays_order(self):
        form = Form(self.env["restaurant.order"].with_user(self.seller))
        with form.order_line_ids.new() as line:
            line.menu_item_id = self.item
            line.qty = 1.0
        order = form.save()
        order.with_user(self.seller).action_pay()
        self.assertEqual(order.state, "paid")
        self.assertEqual(self.ingredient.current_qty, 8.0)

    def test_register_sale_and_refund_update_reports_and_ingredients(self):
        product = self.item.pos_product_id
        self.assertTrue(product)
        self.assertTrue(product.available_in_pos)
        self.assertEqual(product.type, "service")
        self.assertEqual(product.pos_categ_ids.mapped("name"), ["Test Meals"])
        config = self.env["pos.config"].create({"name": "Restaurant Test Register"})
        session = self.env["pos.session"].create({
            "config_id": config.id, "user_id": self.admin.id,
        })
        order = self._make_pos_order(session)
        order.action_pos_order_paid()
        order.action_pos_order_paid()
        self.assertEqual(self.ingredient.current_qty, 8.0)
        moves = self.env["restaurant.pos.consumption"].search([
            ("pos_order_id", "=", order.id),
        ])
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves.company_cost, 6.0)
        self.env.flush_all()
        report = self.env["restaurant.profit.loss.report"].search([
            ("date", "=", fields.Date.today()),
            ("company_id", "=", self.env.company.id),
        ])
        self.assertEqual(report.income, 20.0)
        self.assertEqual(report.ingredient_cost, 6.0)
        self.assertEqual(report.profit, 20.0)

        refund = self._make_pos_order(session, qty=-1.0, refunded_line=order.lines)
        refund.action_pos_order_paid()
        self.assertEqual(self.ingredient.current_qty, 10.0)
        refund_move = self.env["restaurant.pos.consumption"].search([
            ("pos_order_id", "=", refund.id),
        ])
        self.assertEqual(refund_move.qty, -2.0)
        self.assertEqual(refund_move.company_cost, -6.0)
        self.env.flush_all()
        report = self.env["restaurant.profit.loss.report"].search([
            ("date", "=", fields.Date.today()),
            ("company_id", "=", self.env.company.id),
        ])
        report.invalidate_recordset(["income", "ingredient_cost", "profit"])
        self.assertEqual(report.income, 0.0)
        self.assertEqual(report.ingredient_cost, 0.0)
        self.assertEqual(report.profit, 0.0)

    def test_manual_grabfood_order_source_is_saved_and_reported(self):
        config = self.env["pos.config"].create({"name": "GrabFood Register"})
        fields_to_load = self.env["pos.order"]._load_pos_data_fields(config)
        relations = self.env["pos.session"]._load_pos_data_relations(
            "pos.order", fields_to_load
        )
        self.assertIn("source", relations)
        self.assertIn("table_id", relations)
        session = self.env["pos.session"].create({
            "config_id": config.id, "user_id": self.admin.id,
        })
        order = self._make_pos_order(session)
        order.source = "grabfood"
        order.action_pos_order_paid()

        self.assertEqual(order.source, "grabfood")
        self.assertEqual(
            self.env["pos.order"].search([("source", "=", "grabfood")]), order
        )
        today = fields.Date.context_today(
            self.env["restaurant.report.wizard"].with_context(tz="Asia/Yangon")
        )
        wizard = self.env["restaurant.report.wizard"].with_user(self.admin).create({
            "date_from": today, "date_to": today,
            "company_id": self.env.company.id,
        })
        sale = next(
            sale for sale in wizard.get_report_data()["sales"] if sale["name"] == order.name
        )
        self.assertEqual(sale["source"], "GrabFood")

    def test_report_date_range_includes_register_sale_details(self):
        self.admin.tz = "Asia/Yangon"
        config = self.env["pos.config"].create({"name": "Report Range Register"})
        session = self.env["pos.session"].create({
            "config_id": config.id, "user_id": self.admin.id,
        })
        included = self._make_pos_order(session)
        included.action_pos_order_paid()
        included.user_id = self.admin
        today = fields.Date.today()
        included.date_order = datetime.combine(today - timedelta(days=1), time(18, 0))
        excluded = self._make_pos_order(session)
        excluded.action_pos_order_paid()
        excluded.user_id = self.admin
        excluded.date_order = datetime.combine(today - timedelta(days=1), time(16, 0))

        wizard = self.env["restaurant.report.wizard"].with_user(self.admin).create({
            "date_from": today,
            "date_to": today,
            "company_id": self.env.company.id,
        })
        report_data = wizard.get_report_data()
        self.assertEqual(report_data["seller_totals"], [(self.admin, 1, 20.0)])
        self.assertEqual(wizard.income, 20.0)
        self.assertEqual(wizard.ingredient_cost, 6.0)
        self.assertEqual([sale["name"] for sale in report_data["sales"]], [included.name])
        self.assertIn(self.item.name, report_data["sales"][0]["items"])
        action = wizard.action_view_sales()
        visible = self.env["pos.order"].with_user(self.admin).search(action["domain"])
        self.assertEqual(visible, included)
        with self.assertRaises(AccessError):
            wizard.with_user(self.seller).action_view_sales()
        wizard.report_type = "weekly"
        report = self.env.ref("restaurant_pos.action_report_restaurant_financial")
        html, _ = report.with_user(self.admin)._render_qweb_html(
            report.report_name, [wizard.id]
        )
        self.assertIn(self.item.name, html.decode())

    def test_builtin_pos_sales_details_preserves_selected_calendar_dates(self):
        self.admin.tz = "Asia/Yangon"
        start_day = fields.Date.today() - timedelta(days=2)
        end_day = fields.Date.today() - timedelta(days=1)
        config = self.env["pos.config"].create({"name": "POS Details Date Range"})
        form = Form(self.env["pos.details.wizard"].with_user(self.admin))
        form.date_from = start_day
        form.date_to = end_day
        wizard = form.save()

        self.assertEqual(wizard.date_from, start_day)
        self.assertEqual(wizard.date_to, end_day)
        report = wizard.generate_report()
        self.assertEqual(
            fields.Datetime.to_datetime(report["data"]["date_start"]),
            datetime.combine(start_day - timedelta(days=1), time(17, 30)),
        )
        self.assertEqual(
            fields.Datetime.to_datetime(report["data"]["date_stop"]),
            datetime.combine(end_day, time(17, 29, 59)),
        )
        session = self.env["pos.session"].create({
            "config_id": config.id, "user_id": self.admin.id,
        })
        included = self._make_pos_order(session)
        included.action_pos_order_paid()
        included.date_order = datetime.combine(end_day, time(16, 0))
        excluded = self._make_pos_order(session)
        excluded.action_pos_order_paid()
        excluded.date_order = datetime.combine(end_day, time(18, 0))
        details = self.env["report.point_of_sale.report_saledetails"].with_user(self.admin)
        domain = details._get_domain(
            report["data"]["date_start"], report["data"]["date_stop"],
            report["data"]["config_ids"],
        )
        self.assertEqual(self.env["pos.order"].search(domain), included)

    def test_builtin_pos_sales_details_shows_lines_for_selected_days(self):
        self.admin.tz = "Asia/Yangon"
        selected_day = fields.Date.today() - timedelta(days=1)
        config = self.env["pos.config"].create({"name": "Sale Line Preview Register"})
        session = self.env["pos.session"].create({
            "config_id": config.id, "user_id": self.admin.id,
        })
        included = self._make_pos_order(session)
        included.action_pos_order_paid()
        included.date_order = datetime.combine(selected_day, time(16, 0))
        excluded = self._make_pos_order(session)
        excluded.action_pos_order_paid()
        excluded.date_order = datetime.combine(selected_day, time(18, 0))

        form = Form(self.env["pos.details.wizard"].with_user(self.admin))
        form.date_from = selected_day
        form.date_to = selected_day
        self.assertEqual(len(form.sale_line_ids), 1)
        wizard = form.save()
        self.assertEqual(wizard.sale_line_ids, included.lines)
        self.assertEqual(wizard.sale_line_ids.restaurant_sale_date, included.date_order)
        view = self.env["pos.details.wizard"].get_view(view_type="form")
        self.assertIn('name="sale_line_ids"', view["arch"])
        self.assertIn('widget="many2many_tags"', view["arch"])

    def test_register_payment_rejects_insufficient_ingredient_stock(self):
        self.ingredient.current_qty = 1.0
        config = self.env["pos.config"].create({"name": "Stock Test Register"})
        session = self.env["pos.session"].create({
            "config_id": config.id, "user_id": self.admin.id,
        })
        order = self._make_pos_order(session)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            order.action_pos_order_paid()
        order.invalidate_recordset(["state", "restaurant_synced"])
        self.assertEqual(order.state, "draft")
        self.assertFalse(order.restaurant_synced)
        self.assertEqual(self.ingredient.current_qty, 1.0)

    def test_admin_can_remove_ingredient_with_paid_order_history(self):
        order = self._make_order(qty=1.0)
        order.with_user(self.seller).action_pay()
        move = self.env["restaurant.stock.move"].search([
            ("order_id", "=", order.id),
        ])
        self.assertEqual(move.ingredient_id, self.ingredient)

        self.ingredient.with_user(self.admin).unlink()

        self.assertFalse(self.env["restaurant.ingredient"].search([
            ("id", "=", self.ingredient.id),
        ]))
        self.assertFalse(self.env["restaurant.recipe"].search([
            ("ingredient_id", "=", self.ingredient.id),
        ]))
        self.assertEqual(move.ingredient_id, self.ingredient)
        order.with_user(self.admin).action_cancel()
        self.assertTrue(move.reversed)
        self.assertEqual(self.ingredient.current_qty, 10.0)

    def test_admin_can_delete_ingredient_used_only_by_recipe(self):
        ingredient_id = self.ingredient.id
        self.ingredient.with_user(self.admin).unlink()
        self.assertFalse(self.env["restaurant.ingredient"].browse(ingredient_id).exists())
        self.assertFalse(self.env["restaurant.recipe"].search([
            ("ingredient_id", "=", ingredient_id),
        ]))

    def test_admin_can_remove_ingredient_with_register_history(self):
        config = self.env["pos.config"].create({"name": "Ingredient Removal Register"})
        session = self.env["pos.session"].create({
            "config_id": config.id, "user_id": self.admin.id,
        })
        order = self._make_pos_order(session)
        order.action_pos_order_paid()
        move = self.env["restaurant.pos.consumption"].search([
            ("pos_order_id", "=", order.id),
        ])

        self.ingredient.with_user(self.admin).unlink()

        self.assertFalse(self.env["restaurant.ingredient"].search([
            ("id", "=", self.ingredient.id),
        ]))
        self.assertEqual(move.ingredient_id, self.ingredient)
        refund = self._make_pos_order(session, qty=-1.0, refunded_line=order.lines)
        refund.action_pos_order_paid()
        self.assertEqual(self.ingredient.current_qty, 10.0)

    def test_seller_cannot_remove_ingredient_or_its_recipe(self):
        with self.assertRaises(AccessError):
            self.ingredient.with_user(self.seller).unlink()
        self.assertTrue(self.ingredient.exists())
        self.assertTrue(self.env["restaurant.recipe"].search([
            ("ingredient_id", "=", self.ingredient.id),
        ]))

    def test_existing_register_product_can_be_linked_to_menu_item(self):
        generated = self.item.pos_product_id
        existing = self.env["product.product"].create({
            "name": "Existing Register Dish", "list_price": 27.0,
            "type": "service", "available_in_pos": True,
        })
        self.item.pos_product_id = existing
        self.assertFalse(generated.available_in_pos)
        self.assertFalse(self.item.pos_product_managed)
        self.item.price = 25.0
        self.assertEqual(existing.name, "Existing Register Dish")
        self.assertEqual(existing.list_price, 27.0)
        config = self.env["pos.config"].create({"name": "Linked Register"})
        session = self.env["pos.session"].create({
            "config_id": config.id, "user_id": self.admin.id,
        })
        order = self._make_pos_order(session)
        order.action_pos_order_paid()
        self.assertEqual(self.ingredient.current_qty, 8.0)

    def test_menu_image_is_used_by_pos_product(self):
        image_file = BytesIO()
        Image.new("RGB", (32, 32), "#aa5533").save(image_file, format="PNG")
        self.item.image = base64.b64encode(image_file.getvalue())
        self.assertTrue(self.item.pos_product_id.image_128)

        self.item.image = False
        self.assertFalse(self.item.pos_product_id.image_128)

    def test_menu_category_is_available_to_filtered_restaurant_register(self):
        config = self.env["pos.config"].create({
            "name": "Restaurant", "limit_categories": True,
        })
        self.item._sync_pos_products()
        self.assertIn(
            self.item.pos_product_id.pos_categ_ids,
            config.iface_available_categ_ids,
        )

    def test_register_currency_is_loaded_for_cached_browser(self):
        config = self.env["pos.config"].create({"name": "Currency Cache Test"})
        future_sync = fields.Datetime.to_string(
            fields.Datetime.now() + timedelta(days=1)
        )
        currencies = self.env["res.currency"].with_context(
            pos_last_server_date=future_sync
        )._load_pos_data_search_read({"product.pricelist": []}, config)
        self.assertIn(config.currency_id.id, [currency["id"] for currency in currencies])

    def test_table_order_reopens_until_paid_then_table_is_available(self):
        config = self.env["pos.config"].create({
            "name": "Table Workflow Register", "module_pos_restaurant": True,
        })
        floor = self.env["restaurant.floor"].create({
            "name": "Table Workflow Floor",
            "pos_config_ids": [Command.link(config.id)],
        })
        table = self.env["restaurant.table"].create({
            "floor_id": floor.id, "table_number": 42, "seats": 4,
        })
        board = self.env["restaurant.table"].with_user(
            self.seller
        ).get_restaurant_table_board()
        floor_data = next(item for item in board["floors"] if item["id"] == floor.id)
        self.assertEqual(floor_data["tables"][0]["status"], "available")

        first_action = table.with_user(self.seller).action_open_restaurant_order()
        order = self.env["restaurant.order"].browse(first_action["res_id"])
        self.assertEqual(order.table_id, table)
        self.assertEqual(order.state, "draft")
        self.assertEqual(
            table.with_user(self.seller).action_open_restaurant_order()["res_id"],
            order.id,
        )
        with self.assertRaises(UserError):
            self.env["restaurant.order"].with_user(self.seller).create({
                "table_id": table.id,
            })

        order.with_user(self.seller).write({
            "order_line_ids": [Command.create({
                "menu_item_id": self.item.id, "qty": 1.0,
            })],
        })
        board = self.env["restaurant.table"].with_user(
            self.seller
        ).get_restaurant_table_board()
        floor_data = next(item for item in board["floors"] if item["id"] == floor.id)
        self.assertEqual(floor_data["tables"][0]["status"], "occupied")
        self.assertEqual(floor_data["tables"][0]["total"], 20.0)

        with self.assertRaises(UserError):
            floor.with_user(self.admin).write({"active": False})

        order.with_user(self.seller).action_pay()
        self.assertEqual(self.ingredient.current_qty, 8.0)
        self.assertEqual(table.restaurant_status, "available")
        next_action = table.with_user(self.seller).action_open_restaurant_order()
        self.assertNotEqual(next_action["res_id"], order.id)
        self.assertFalse(self._make_order(qty=1.0).table_id)

    def test_table_menu_cart_and_cash_checkout(self):
        floor = self.env["restaurant.floor"].create({"name": "Menu Checkout Floor"})
        table = self.env["restaurant.table"].create({
            "floor_id": floor.id, "table_number": 7, "seats": 2,
        })
        order_id = table.with_user(self.seller).action_open_restaurant_order()["res_id"]
        order = self.env["restaurant.order"].browse(order_id).with_user(self.seller)
        self.assertEqual(table.restaurant_status, "available")
        screen = order.get_table_order_screen()
        self.assertEqual(screen["order"]["table_number"], 7)
        self.assertIn(self.item.id, [item["id"] for item in screen["items"]])

        unavailable = self.env["restaurant.menu.item"].create({
            "name": "Sold Out", "category_id": self.category.id,
            "price": 10.0, "in_stock": False,
        })
        self.assertNotIn(
            unavailable.id,
            [item["id"] for item in order.get_table_order_screen()["items"]],
        )
        with self.assertRaises(UserError):
            order.add_table_menu_item(unavailable.id)

        cart = order.add_table_menu_item(self.item.id)
        self.assertEqual(cart["total"], 20.0)
        self.assertEqual(table.restaurant_status, "occupied")
        cart = order.add_table_menu_item(self.item.id)
        self.assertEqual(len(cart["lines"]), 1)
        self.assertEqual(cart["lines"][0]["qty"], 2.0)
        self.assertEqual(cart["total"], 40.0)
        self.assertEqual(
            table.with_user(self.seller).action_open_restaurant_order()["res_id"], order.id
        )
        cart = order.set_table_line_quantity(cart["lines"][0]["id"], 1)
        self.assertEqual(cart["total"], 20.0)
        cart = order.set_table_line_quantity(cart["lines"][0]["id"], 0)
        self.assertFalse(cart["lines"])
        self.assertEqual(table.restaurant_status, "available")
        cart = order.add_table_menu_item(self.item.id)
        self.assertEqual(cart["total"], 20.0)
        with self.assertRaises(UserError):
            order.pay_table_order(19.0)

        receipt = order.pay_table_order(25.0)
        self.assertEqual(receipt["cash_received"], 25.0)
        self.assertEqual(receipt["change"], 5.0)
        self.assertEqual(order.state, "paid")
        self.assertEqual(self.ingredient.current_qty, 8.0)
        self.assertEqual(table.restaurant_status, "available")
        with self.assertRaises(UserError):
            order.add_table_menu_item(self.item.id)

    def test_stock_deduction_and_admin_cancellation(self):
        order = self._make_order()
        order.with_user(self.seller).action_pay()
        self.assertEqual(order.state, "paid")
        self.assertEqual(self.ingredient.current_qty, 6.0)
        move = self.env["restaurant.stock.move"].search([("order_id", "=", order.id)])
        self.assertEqual(move.qty, 4.0)
        self.assertEqual(move.total_cost, 12.0)
        order.with_user(self.admin).action_cancel()
        self.assertEqual(order.state, "cancelled")
        self.assertEqual(self.ingredient.current_qty, 10.0)
        self.assertTrue(move.reversed)

    def test_payment_rejects_insufficient_stock(self):
        self.ingredient.current_qty = 1.0
        order = self._make_order()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            order.with_user(self.seller).action_pay()
        order.invalidate_recordset(["state"])
        self.assertEqual(order.state, "draft")
        self.assertEqual(self.ingredient.current_qty, 1.0)

    def test_profit_loss(self):
        order = self._make_order()
        order.with_user(self.seller).action_pay()
        self.env["restaurant.expense"].with_user(self.admin).create({
            "description": "Test utility bill",
            "amount": 5.0,
            "date": fields.Date.today(),
        })
        self.env.flush_all()
        report = self.env["restaurant.profit.loss.report"].with_user(self.admin).search([
            ("date", "=", fields.Date.today()),
            ("company_id", "=", self.env.company.id),
        ])
        self.assertEqual(len(report), 1)
        self.assertAlmostEqual(report.income, 40.0)
        self.assertAlmostEqual(report.expenses, 5.0)
        self.assertAlmostEqual(report.ingredient_cost, 12.0)
        self.assertAlmostEqual(report.profit, 35.0)
        daily = self.env["restaurant.daily.income"].with_user(self.admin).search([
            ("date", "=", fields.Date.today()),
            ("seller_id", "=", self.seller.id),
            ("company_id", "=", self.env.company.id),
        ])
        self.assertEqual(daily.order_count, 1)
        self.assertAlmostEqual(daily.total_cash, 40.0)
        dashboard = self.env["restaurant.dashboard"].with_user(self.admin).get_summary()
        self.assertAlmostEqual(dashboard["today_income"], 40.0)
        self.assertAlmostEqual(dashboard["today_profit"], 35.0)

    def test_daily_purchases_and_sales_make_cash_profit(self):
        self.item.price = 5000.0
        config = self.env["pos.config"].create({"name": "Daily Cash Register"})
        session = self.env["pos.session"].create({
            "config_id": config.id, "user_id": self.admin.id,
        })
        order = self._make_pos_order(session)
        order.action_pos_order_paid()
        today = fields.Date.context_today(
            self.env["restaurant.expense"].with_context(tz="Asia/Yangon")
        )
        eggs = self.env["restaurant.expense"].with_user(self.admin).create({
            "date": today, "description": "Eggs", "category": "ingredient_purchase",
            "quantity": 10, "amount": 1000,
        })
        noodles = self.env["restaurant.expense"].with_user(self.admin).create({
            "date": today, "description": "Dry noodles", "category": "ingredient_purchase",
            "quantity": 1, "amount": 2000,
        })
        self.assertEqual(eggs.unit_price, 100.0)
        self.assertEqual(noodles.unit_price, 2000.0)
        self.env.flush_all()
        report = self.env["restaurant.profit.loss.report"].with_user(self.admin).search([
            ("date", "=", today), ("company_id", "=", self.env.company.id),
        ])
        self.assertEqual(report.income, 5000.0)
        self.assertEqual(report.expenses, 3000.0)
        self.assertEqual(report.ingredient_cost, 6.0)
        self.assertEqual(report.profit, 2000.0)
        wizard = self.env["restaurant.report.wizard"].with_user(self.admin).create({
            "date_from": today, "date_to": today,
            "company_id": self.env.company.id,
        })
        self.assertEqual(wizard.income, 5000.0)
        self.assertEqual(wizard.expenses, 3000.0)
        self.assertEqual(wizard.profit, 2000.0)
        dashboard = self.env["restaurant.dashboard"].with_user(self.admin).get_summary()
        self.assertEqual(dashboard["today_expenses"], 3000.0)
        self.assertEqual(dashboard["today_profit"], 2000.0)

    def test_pos_sale_uses_company_local_day_in_reports(self):
        config = self.env["pos.config"].create({"name": "Local Day Register"})
        session = self.env["pos.session"].create({
            "config_id": config.id, "user_id": self.admin.id,
        })
        order = self._make_pos_order(session)
        order.action_pos_order_paid()
        local_day = fields.Date.today() - timedelta(days=1)
        order.date_order = datetime.combine(local_day, time(18, 0))
        self.env.flush_all()
        report = self.env["restaurant.profit.loss.report"].with_user(self.admin).search([
            ("date", "=", local_day + timedelta(days=1)),
            ("company_id", "=", self.env.company.id),
        ])
        daily = self.env["restaurant.daily.income"].with_user(self.admin).search([
            ("date", "=", local_day + timedelta(days=1)),
            ("company_id", "=", self.env.company.id),
        ])
        self.assertEqual(report.income, 20.0)
        self.assertEqual(daily.total_cash, 20.0)

    def test_seller_access(self):
        with self.assertRaises(AccessError):
            self.env["restaurant.menu.item"].with_user(self.seller).create({
                "name": "Forbidden Item", "category_id": self.category.id, "price": 1.0,
            })
        self.assertEqual(
            self.env["restaurant.ingredient"].with_user(self.seller).search_count([]), 1
        )
        own_expense = self.env["restaurant.expense"].with_user(self.seller).create({
            "description": "Seller expense", "amount": 2.0,
        })
        other_expense = self.env["restaurant.expense"].with_user(self.admin).create({
            "description": "Admin expense", "amount": 3.0,
        })
        visible = self.env["restaurant.expense"].with_user(self.seller).search([])
        self.assertIn(own_expense.id, visible.ids)
        self.assertNotIn(other_expense.id, visible.ids)
        with self.assertRaises(AccessError):
            own_expense.with_user(self.seller).unlink()
        order = self._make_order()
        with self.assertRaises(AccessError):
            order.with_user(self.seller).action_cancel()
        with self.assertRaises(AccessError):
            self.env["restaurant.profit.loss.report"].with_user(self.seller).search([])
        with self.assertRaises(AccessError):
            self.env["restaurant.dashboard"].with_user(self.seller).get_summary()

    def test_builtin_pos_is_primary_app_for_restaurant_staff(self):
        self.assertTrue(self.seller.has_group("point_of_sale.group_pos_user"))
        self.assertTrue(self.admin.has_group("point_of_sale.group_pos_manager"))
        self.assertFalse(self.env.ref("restaurant_pos.menu_restaurant_pos_root").active)
        operations = self.env.ref("restaurant_pos.menu_pos_restaurant_operations")
        self.assertTrue(operations.active)
        self.assertEqual(
            operations.parent_id, self.env.ref("point_of_sale.menu_point_root")
        )
