"""Daily cash profit measures that graph and pivot views can group by period."""

from odoo import fields, models, tools


class RestaurantProfitLossReport(models.Model):
    _name = "restaurant.profit.loss.report"
    _description = "Restaurant Profit and Loss"
    _auto = False
    _order = "date desc, company_id"

    date = fields.Date(readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    income = fields.Monetary(readonly=True, currency_field="currency_id")
    expenses = fields.Monetary(readonly=True, currency_field="currency_id")
    ingredient_cost = fields.Monetary(
        string="Recipe Cost (Reference)", readonly=True, currency_field="currency_id"
    )
    profit = fields.Monetary(
        string="Cash Profit / Loss", readonly=True, currency_field="currency_id"
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE VIEW {self._table} AS (
                SELECT ROW_NUMBER() OVER (ORDER BY report_date, company_id) AS id,
                       report_date AS date,
                       company_id,
                       currency_id,
                       SUM(income) AS income,
                       SUM(expenses) AS expenses,
                       SUM(ingredient_cost) AS ingredient_cost,
                       SUM(income - expenses) AS profit
                  FROM (
                    SELECT (o.order_date AT TIME ZONE 'UTC' AT TIME ZONE
                            COALESCE(NULLIF(cp.tz, ''), 'Asia/Yangon'))::date AS report_date,
                           o.company_id,
                           o.company_currency_id AS currency_id,
                           o.company_amount AS income,
                           0.0::numeric AS expenses,
                           0.0::numeric AS ingredient_cost
                     FROM restaurant_order o
                     JOIN res_company c ON c.id = o.company_id
                     JOIN res_partner cp ON cp.id = c.partner_id
                     WHERE o.state = 'paid'
                    UNION ALL
                    SELECT (p.date_order AT TIME ZONE 'UTC' AT TIME ZONE
                            COALESCE(NULLIF(cp.tz, ''), 'Asia/Yangon'))::date,
                           p.company_id, c.currency_id,
                           p.amount_total / NULLIF(p.currency_rate, 0),
                           0.0::numeric, 0.0::numeric
                      FROM pos_order p
                      JOIN res_company c ON c.id = p.company_id
                      JOIN res_partner cp ON cp.id = c.partner_id
                     WHERE p.state IN ('paid', 'done')
                    UNION ALL
                    SELECT e.date, e.company_id, e.company_currency_id,
                           0.0::numeric, e.company_amount, 0.0::numeric
                      FROM restaurant_expense e
                    UNION ALL
                    SELECT (o.order_date AT TIME ZONE 'UTC' AT TIME ZONE
                            COALESCE(NULLIF(cp.tz, ''), 'Asia/Yangon'))::date,
                           o.company_id,
                           o.company_currency_id,
                           0.0::numeric, 0.0::numeric, m.company_cost
                      FROM restaurant_stock_move m
                      JOIN restaurant_order o ON o.id = m.order_id
                      JOIN res_company c ON c.id = o.company_id
                      JOIN res_partner cp ON cp.id = c.partner_id
                     WHERE o.state = 'paid' AND NOT m.reversed
                    UNION ALL
                    SELECT (p.date_order AT TIME ZONE 'UTC' AT TIME ZONE
                            COALESCE(NULLIF(cp.tz, ''), 'Asia/Yangon'))::date,
                           p.company_id, c.currency_id,
                           0.0::numeric, 0.0::numeric, m.company_cost
                      FROM restaurant_pos_consumption m
                      JOIN pos_order p ON p.id = m.pos_order_id
                      JOIN res_company c ON c.id = p.company_id
                      JOIN res_partner cp ON cp.id = c.partner_id
                     WHERE p.state IN ('paid', 'done')
                  ) entries
                 GROUP BY report_date, company_id, currency_id
            )
        """)
