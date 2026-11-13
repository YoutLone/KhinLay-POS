"""Keep the POS register's currency available to cached browser sessions."""

from odoo import api, models


class ResCurrency(models.Model):
    _inherit = "res.currency"

    @api.model
    def _load_pos_data_search_read(self, data, config):
        # The register config is always loaded, so its currency must be loaded
        # even when the browser asks only for records changed since last sync.
        return super(ResCurrency, self.with_context(
            pos_limited_loading=False
        ))._load_pos_data_search_read(data, config)
