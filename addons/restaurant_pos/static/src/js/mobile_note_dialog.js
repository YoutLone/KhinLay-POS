import { onMounted, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";

patch(TextInputPopup.prototype, {
    setup() {
        super.setup(...arguments);

        let dialog;
        const viewport = window.visualViewport;
        const updateViewport = () => {
            if (!dialog) {
                return;
            }
            const visibleHeight = viewport?.height ?? window.innerHeight;
            const visibleTop = viewport?.offsetTop ?? 0;
            const keyboardInset = Math.max(0, window.innerHeight - visibleTop - visibleHeight);
            dialog.style.setProperty("--restaurant-pos-visible-height", `${Math.max(0, visibleHeight - 8)}px`);
            dialog.style.setProperty("--restaurant-pos-keyboard-inset", `${keyboardInset}px`);
        };

        onMounted(() => {
            dialog = this.inputRef.el?.closest(".modal-dialog");
            if (!dialog) {
                return;
            }
            dialog.classList.add("restaurant-pos-text-input-dialog");
            updateViewport();
            viewport?.addEventListener("resize", updateViewport);
            viewport?.addEventListener("scroll", updateViewport);
            window.addEventListener("resize", updateViewport);
        });
        onWillUnmount(() => {
            viewport?.removeEventListener("resize", updateViewport);
            viewport?.removeEventListener("scroll", updateViewport);
            window.removeEventListener("resize", updateViewport);
        });
    },
});
