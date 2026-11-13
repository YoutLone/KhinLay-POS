"""Restaurant operating expenses and receipt attachments."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class RestaurantExpense(models.Model):
    _name = "restaurant.expense"
    _description = "Restaurant Expense"
    _order = "date desc, id desc"

    description = fields.Char(string="Item or Expense", required=True)
    quantity = fields.Float(required=True, default=1.0)
    amount = fields.Monetary(
        string="Total Paid", required=True, currency_field="currency_id"
    )
    unit_price = fields.Monetary(
        string="Price per Unit", compute="_compute_unit_price", currency_field="currency_id"
    )
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    company_currency_id = fields.Many2one(
        "res.currency", string="Company Currency",
        related="company_id.currency_id", store=True, readonly=True
    )
    company_amount = fields.Monetary(
        compute="_compute_company_amount", store=True, currency_field="company_currency_id"
    )
    date = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(
            self.with_context(tz=self.env.company.partner_id.tz or "Asia/Yangon")
        ),
        index=True,
    )
    category = fields.Selection(
        [("ingredient_purchase", "Ingredient Purchase"), ("other", "Other")],
        required=True,
        default="other",
    )
    purchased_by = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, index=True
    )
    receipt = fields.Binary(attachment=True)
    receipt_filename = fields.Char()

    _amount_positive = models.Constraint(
        "CHECK(amount > 0)", "Expense amount must be greater than zero."
    )
    _quantity_positive = models.Constraint(
        "CHECK(quantity > 0)", "Expense quantity must be greater than zero."
    )

    @api.depends("amount", "quantity")
    def _compute_unit_price(self):
        for expense in self:
            expense.unit_price = expense.amount / expense.quantity if expense.quantity else 0.0

    @api.depends("amount", "currency_id", "company_id", "date")
    def _compute_company_amount(self):
        for expense in self:
            expense.company_amount = expense.currency_id._convert(
                expense.amount,
                expense.company_id.currency_id,
                expense.company_id,
                expense.date,
            ) if expense.currency_id and expense.company_id and expense.date else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        is_admin = self.env.user.has_group("restaurant_pos.group_restaurant_admin")
        prepared = []
        for values in vals_list:
            vals = dict(values)
            vals.pop("company_amount", None)
            vals.pop("company_currency_id", None)
            if not is_admin:
                vals["purchased_by"] = self.env.user.id
                vals["company_id"] = self.env.company.id
                vals["currency_id"] = self.env.company.currency_id.id
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if set(vals) & {"company_amount", "company_currency_id"}:
            raise UserError("Converted expense amounts are managed automatically.")
        if not self.env.user.has_group("restaurant_pos.group_restaurant_admin"):
            allowed = {
                "description", "quantity", "amount", "date", "category", "receipt", "receipt_filename"
            }
            if set(vals) - allowed:
                raise AccessError("Sellers may only edit their own expense details.")
        return super().write(vals)
