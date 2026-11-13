/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class RestaurantDashboard extends Component {
    static template = "restaurant_pos.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.state = useState({ loading: true, summary: null, error: null });
        onWillStart(() => this.loadSummary());
    }

    async loadSummary() {
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.summary = await this.orm.call("restaurant.dashboard", "get_summary", []);
        } catch (error) {
            this.state.error = error.message || "Could not load the dashboard.";
        } finally {
            this.state.loading = false;
        }
    }

    formatMoney(amount) {
        const currency = this.state.summary?.currency_code || "MMK";
        return new Intl.NumberFormat(undefined, {
            style: "currency",
            currency,
        }).format(amount || 0);
    }
}

registry.category("actions").add("restaurant_pos.Dashboard", RestaurantDashboard);
