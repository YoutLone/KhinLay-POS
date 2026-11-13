"""Daily manual and register sales by seller, in the company currency."""

from odoo import fields, models, tools


class RestaurantDailyIncome(models.Model):
    _name = "restaurant.daily.income"
    _description = "Restaurant Daily Income"
    _auto = False
    _order = "date desc, seller_id"

    date = fields.Date(readonly=True)
    seller_id = fields.Many2one("res.users", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    total_cash = fields.Monetary(
        string="Total Sales", readonly=True, currency_field="currency_id"
    )
    order_count = fields.Integer(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE VIEW {self._table} AS (
                SELECT ROW_NUMBER() OVER (ORDER BY date, company_id, seller_id) AS id,
                       date, seller_id, company_id, currency_id,
                       SUM(amount) AS total_cash,
                       COUNT(*) AS order_count
                  FROM (
                    SELECT (o.order_date AT TIME ZONE 'UTC' AT TIME ZONE
                            COALESCE(NULLIF(cp.tz, ''), 'Asia/Yangon'))::date AS date,
                           o.seller_id, o.company_id,
                           o.company_currency_id AS currency_id,
                           o.company_amount AS amount
                      FROM restaurant_order o
                      JOIN res_company c ON c.id = o.company_id
                      JOIN res_partner cp ON cp.id = c.partner_id
                     WHERE o.state = 'paid'
                    UNION ALL
                    SELECT (p.date_order AT TIME ZONE 'UTC' AT TIME ZONE
                            COALESCE(NULLIF(cp.tz, ''), 'Asia/Yangon'))::date,
                           p.user_id, p.company_id,
                           c.currency_id,
                           p.amount_total / NULLIF(p.currency_rate, 0)
                      FROM pos_order p
                      JOIN res_company c ON c.id = p.company_id
                      JOIN res_partner cp ON cp.id = c.partner_id
                     WHERE p.state IN ('paid', 'done')
                  ) sales
                 GROUP BY date, seller_id, company_id, currency_id
            )
        """)
