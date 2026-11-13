/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    toggleGrabFoodSource() {
        const order = this.currentOrder;
        order.source = order.source === "grabfood" ? "pos" : "grabfood";
    },
});
