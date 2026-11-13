"""Use whole local calendar days in the standard POS Sales Details report."""

from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError


class PosDetailsWizard(models.TransientModel):
    _inherit = "pos.details.wizard"

    date_from = fields.Date(string="First Day", required=True, default=fields.Date.context_today)
    date_to = fields.Date(string="Last Day", required=True, default=fields.Date.context_today)
    sale_line_ids = fields.Many2many(
        "pos.order.line", string="Sales in Selected Dates", compute="_compute_sale_line_ids"
    )

    def _selected_dates_utc(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError("The start date must not be after the end date.")

        user_tz = self.env.tz
        start = user_tz.localize(datetime.combine(self.date_from, time.min))
        end = user_tz.localize(datetime.combine(self.date_to + timedelta(days=1), time.min))
        date_start = start.astimezone(pytz.UTC).replace(tzinfo=None)
        date_stop = end.astimezone(pytz.UTC).replace(tzinfo=None) - timedelta(seconds=1)
        return date_start, date_stop

    @api.depends("date_from", "date_to", "pos_config_ids")
    @api.depends_context("tz")
    def _compute_sale_line_ids(self):
        for wizard in self:
            if not wizard.date_from or not wizard.date_to or wizard.date_from > wizard.date_to:
                wizard.sale_line_ids = False
                continue
            date_start, date_stop = wizard._selected_dates_utc()
            domain = [
                ("state", "in", ["paid", "done"]),
                ("date_order", ">=", date_start),
                ("date_order", "<=", date_stop),
            ]
            if wizard.pos_config_ids:
                domain.append(("config_id", "in", wizard.pos_config_ids.ids))
            wizard.sale_line_ids = self.env["pos.order"].search(domain).lines

    def generate_report(self):
        self.ensure_one()
        date_start, date_stop = self._selected_dates_utc()
        data = {
            "date_start": fields.Datetime.to_string(date_start),
            "date_stop": fields.Datetime.to_string(date_stop),
            "config_ids": self.pos_config_ids.ids,
        }
        return self.env.ref("point_of_sale.sale_details_report").report_action([], data=data)
