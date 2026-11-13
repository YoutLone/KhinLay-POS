"""Admin-only summary data for the OWL dashboard."""

from odoo import api, fields, models
from odoo.exceptions import AccessError


class RestaurantDashboard(models.AbstractModel):
    _name = "restaurant.dashboard"
    _description = "Restaurant Dashboard Data"

    @api.model
    def get_summary(self):
        if not self.env.user.has_group("restaurant_pos.group_restaurant_admin"):
            raise AccessError("Only Restaurant Admin can view the dashboard.")
        self.env.flush_all()
        company = self.env.company
        today = fields.Date.context_today(
            self.with_context(tz=company.partner_id.tz or "Asia/Yangon")
        )
        self.env.cr.execute(
            """SELECT income, expenses, profit
                 FROM restaurant_profit_loss_report
                WHERE date = %s AND company_id = %s""",
            [today, company.id],
        )
        row = self.env.cr.fetchone() or (0.0, 0.0, 0.0)
        self.env.cr.execute(
            """SELECT COALESCE(SUM(order_count), 0)
                 FROM restaurant_daily_income
                WHERE date = %s AND company_id = %s""",
            [today, company.id],
        )
        paid_orders = int(self.env.cr.fetchone()[0] or 0)
        return {
            "date": fields.Date.to_string(today),
            "currency_code": company.currency_id.name,
            "today_income": float(row[0]),
            "today_expenses": float(row[1]),
            "today_profit": float(row[2]),
            "paid_orders": paid_orders,
            "low_stock_count": self.env["restaurant.ingredient"].search_count([
                ("is_low_stock", "=", True)
            ]),
        }
