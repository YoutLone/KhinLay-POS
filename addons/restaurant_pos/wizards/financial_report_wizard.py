"""Date-range financial report and PDF entry point."""

from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class RestaurantReportWizard(models.TransientModel):
    _name = "restaurant.report.wizard"
    _description = "Restaurant Financial Report Wizard"

    report_type = fields.Selection(
        [("daily", "Daily Profit and Loss"), ("weekly", "Weekly Profit and Loss"),
         ("monthly", "Monthly Profit and Loss")],
        required=True,
        default="daily",
    )
    date_from = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(
            self.with_context(tz=self.env.company.partner_id.tz or "Asia/Yangon")
        ),
    )
    date_to = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(
            self.with_context(tz=self.env.company.partner_id.tz or "Asia/Yangon")
        ),
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", readonly=True
    )
    income = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    expenses = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    ingredient_cost = fields.Monetary(
        string="Recipe Cost (Reference)", compute="_compute_totals", currency_field="currency_id"
    )
    profit = fields.Monetary(
        string="Cash Profit / Loss", compute="_compute_totals", currency_field="currency_id"
    )

    @api.onchange("report_type")
    def _onchange_report_type(self):
        today = fields.Date.context_today(
            self.with_context(tz=self.company_id.partner_id.tz or "Asia/Yangon")
        )
        if self.report_type == "weekly":
            self.date_from = today - timedelta(days=today.weekday())
            self.date_to = self.date_from + timedelta(days=6)
        elif self.report_type == "monthly":
            self.date_from = today.replace(day=1)
            self.date_to = (self.date_from.replace(day=28) + timedelta(days=4)).replace(
                day=1
            ) - timedelta(days=1)
        else:
            self.date_from = today
            self.date_to = today

    @api.depends("date_from", "date_to", "company_id")
    def _compute_totals(self):
        for wizard in self:
            totals = wizard._report_totals()
            wizard.income = totals[0]
            wizard.expenses = totals[1]
            wizard.ingredient_cost = totals[2]
            wizard.profit = totals[3]

    def _report_totals(self):
        self.ensure_one()
        if not self.date_from or not self.date_to or not self.company_id:
            return (0.0, 0.0, 0.0, 0.0)
        start, end = self._date_bounds()
        self.env.flush_all()
        self.env.cr.execute(
            """SELECT COALESCE(SUM(income), 0), COALESCE(SUM(expenses), 0),
                      COALESCE(SUM(ingredient_cost), 0),
                      COALESCE(SUM(income - expenses), 0)
                 FROM (
                    SELECT o.company_amount AS income, 0::numeric AS expenses,
                           0::numeric AS ingredient_cost
                      FROM restaurant_order o
                     WHERE o.state = 'paid' AND o.company_id = %s
                       AND o.order_date >= %s AND o.order_date < %s
                    UNION ALL
                    SELECT p.amount_total / NULLIF(p.currency_rate, 0),
                           0::numeric, 0::numeric
                      FROM pos_order p
                     WHERE p.state IN ('paid', 'done') AND p.company_id = %s
                       AND p.date_order >= %s AND p.date_order < %s
                    UNION ALL
                    SELECT 0::numeric, e.company_amount, 0::numeric
                      FROM restaurant_expense e
                     WHERE e.company_id = %s AND e.date BETWEEN %s AND %s
                    UNION ALL
                    SELECT 0::numeric, 0::numeric, m.company_cost
                      FROM restaurant_stock_move m
                      JOIN restaurant_order o ON o.id = m.order_id
                     WHERE o.state = 'paid' AND NOT m.reversed
                       AND o.company_id = %s
                       AND o.order_date >= %s AND o.order_date < %s
                    UNION ALL
                    SELECT 0::numeric, 0::numeric, m.company_cost
                      FROM restaurant_pos_consumption m
                      JOIN pos_order p ON p.id = m.pos_order_id
                     WHERE p.state IN ('paid', 'done') AND p.company_id = %s
                       AND p.date_order >= %s AND p.date_order < %s
                 ) entries""",
            [
                self.company_id.id, start, end,
                self.company_id.id, start, end,
                self.company_id.id, self.date_from, self.date_to,
                self.company_id.id, start, end,
                self.company_id.id, start, end,
            ],
        )
        return self.env.cr.fetchone()

    def _check_admin(self):
        if not self.env.user.has_group("restaurant_pos.group_restaurant_admin"):
            raise AccessError("Only Restaurant Admin can view financial reports.")

    def _date_bounds(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError("Choose a start and end date.")
        if self.date_from > self.date_to:
            raise UserError("The start date must not be after the end date.")
        company_tz = pytz.timezone(self.company_id.partner_id.tz or "Asia/Yangon")
        start = company_tz.localize(datetime.combine(self.date_from, time.min))
        end = company_tz.localize(datetime.combine(self.date_to + timedelta(days=1), time.min))
        return (
            start.astimezone(pytz.UTC).replace(tzinfo=None),
            end.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    def get_report_data(self):
        self.ensure_one()
        self._check_admin()
        start, end = self._date_bounds()
        orders = self.env["restaurant.order"].search([
            ("state", "=", "paid"), ("company_id", "=", self.company_id.id),
            ("order_date", ">=", start), ("order_date", "<", end),
        ], order="order_date, id")
        pos_orders = self.env["pos.order"].search([
            ("state", "in", ["paid", "done"]),
            ("company_id", "=", self.company_id.id),
            ("date_order", ">=", start), ("date_order", "<", end),
        ], order="date_order, id")
        seller_totals = defaultdict(lambda: [0, 0.0])
        sellers = {}
        sales = []
        report_context = self.with_context(tz=self.company_id.partner_id.tz or "Asia/Yangon")
        for order in orders:
            seller_id = order.seller_id.id
            sellers[seller_id] = order.seller_id
            seller_totals[seller_id][0] += 1
            seller_totals[seller_id][1] += order.company_amount
            sales.append({
                "name": order.name,
                "date": fields.Datetime.context_timestamp(report_context, order.order_date).strftime("%Y-%m-%d %H:%M"),
                "seller": order.seller_id.name,
                "source": "Legacy",
                "items": ", ".join(
                    "%s × %s" % (line.menu_item_id.display_name, line.qty)
                    for line in order.order_line_ids
                ),
                "amount": order.company_amount,
                "sort_date": order.order_date,
            })
        for order in pos_orders:
            seller_id = order.user_id.id
            sellers[seller_id] = order.user_id
            amount = order.amount_total / order.currency_rate if order.currency_rate else 0.0
            seller_totals[seller_id][0] += 1
            seller_totals[seller_id][1] += amount
            sales.append({
                "name": order.name,
                "date": fields.Datetime.context_timestamp(report_context, order.date_order).strftime("%Y-%m-%d %H:%M"),
                "seller": order.user_id.name,
                "source": "GrabFood" if order.source == "grabfood" else "POS",
                "items": ", ".join(
                    "%s × %s" % (line.product_id.display_name, line.qty)
                    for line in order.lines
                ),
                "amount": amount,
                "sort_date": order.date_order,
            })
        sales.sort(key=lambda sale: (sale["sort_date"], sale["name"]))
        return {
            "orders": orders,
            "sales": sales,
            "seller_totals": [
                (sellers[seller_id], values[0], values[1])
                for seller_id, values in sorted(
                    seller_totals.items(), key=lambda item: sellers[item[0]].name
                )
            ],
        }

    def action_view_sales(self):
        self.ensure_one()
        self._check_admin()
        start, end = self._date_bounds()
        return {
            "type": "ir.actions.act_window",
            "name": "Sales Details",
            "res_model": "pos.order",
            "view_mode": "list,form",
            "domain": [
                ("state", "in", ["paid", "done"]),
                ("company_id", "=", self.company_id.id),
                ("date_order", ">=", fields.Datetime.to_string(start)),
                ("date_order", "<", fields.Datetime.to_string(end)),
            ],
            "target": "current",
        }

    def action_print(self):
        self.ensure_one()
        self._check_admin()
        self._report_totals()
        return self.env.ref("restaurant_pos.action_report_restaurant_financial").report_action(
            self
        )
