/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class RestaurantTables extends Component {
    static template = "restaurant_pos.Tables";

    setup() {
        this.loadBoard = this.loadBoard.bind(this);
        this.selectFloor = this.selectFloor.bind(this);
        this.openTable = this.openTable.bind(this);
        this.backToTables = this.backToTables.bind(this);
        this.backToOrder = this.backToOrder.bind(this);
        this.selectCategory = this.selectCategory.bind(this);
        this.onSearchInput = this.onSearchInput.bind(this);
        this.addItem = this.addItem.bind(this);
        this.changeQuantity = this.changeQuantity.bind(this);
        this.startPayment = this.startPayment.bind(this);
        this.onTenderedInput = this.onTenderedInput.bind(this);
        this.confirmPayment = this.confirmPayment.bind(this);
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            view: "tables",
            floors: [],
            activeFloorId: null,
            busyTableId: null,
            busy: false,
            currency: "MMK",
            error: null,
            order: null,
            categories: [],
            items: [],
            activeCategoryId: null,
            search: "",
            tendered: "",
            receipt: null,
        });
        onWillStart(() => this.loadBoard());
    }

    get currentFloor() {
        return this.state.floors.find((floor) => floor.id === this.state.activeFloorId);
    }

    get visibleItems() {
        const query = this.state.search.trim().toLocaleLowerCase();
        return this.state.items.filter((item) =>
            (!this.state.activeCategoryId || item.category_id === this.state.activeCategoryId) &&
            (!query || item.name.toLocaleLowerCase().includes(query) ||
                item.description.toLocaleLowerCase().includes(query))
        );
    }

    get changeDue() {
        return Math.max(0, Number(this.state.tendered || 0) - (this.state.order?.total || 0));
    }

    async loadBoard() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const board = await this.orm.call("restaurant.table", "get_restaurant_table_board", []);
            this.state.floors = board.floors;
            this.state.currency = board.currency;
            if (!board.floors.some((floor) => floor.id === this.state.activeFloorId)) {
                this.state.activeFloorId = board.floors[0]?.id || null;
            }
        } catch (error) {
            this.state.error = error.message || "Could not load dining tables.";
        } finally {
            this.state.loading = false;
        }
    }

    selectFloor(floorId) {
        this.state.activeFloorId = floorId;
    }

    async openTable(table) {
        if (this.state.busyTableId !== null) {
            return;
        }
        this.state.busyTableId = table.id;
        this.state.error = null;
        try {
            const action = await this.orm.call(
                "restaurant.table", "action_open_restaurant_order", [[table.id]]
            );
            await this.loadOrder(action.res_id);
        } catch (error) {
            await this.loadBoard();
            this.state.error = error.data?.message || error.message || "Could not open this table.";
        } finally {
            this.state.busyTableId = null;
        }
    }

    async loadOrder(orderId) {
        const screen = await this.orm.call("restaurant.order", "get_table_order_screen", [[orderId]]);
        this.state.order = screen.order;
        this.state.categories = screen.categories;
        this.state.items = screen.items;
        this.state.currency = screen.order.currency;
        this.state.activeCategoryId = null;
        this.state.search = "";
        this.state.view = "order";
    }

    async backToTables() {
        if (this.state.busy) {
            return;
        }
        await this.loadBoard();
        this.state.view = "tables";
        this.state.order = null;
        this.state.receipt = null;
    }

    backToOrder() {
        this.state.error = null;
        this.state.view = "order";
    }

    selectCategory(categoryId) {
        this.state.activeCategoryId = categoryId;
    }

    onSearchInput(event) {
        this.state.search = event.target.value;
    }

    async addItem(item) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = null;
        try {
            this.state.order = await this.orm.call(
                "restaurant.order", "add_table_menu_item", [[this.state.order.id], item.id]
            );
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not add this item.";
        } finally {
            this.state.busy = false;
        }
    }

    async changeQuantity(line, change) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = null;
        try {
            this.state.order = await this.orm.call(
                "restaurant.order", "set_table_line_quantity",
                [[this.state.order.id], line.id, Math.max(0, line.qty + change)]
            );
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not change quantity.";
        } finally {
            this.state.busy = false;
        }
    }

    startPayment() {
        if (!this.state.order?.lines.length || this.state.busy) {
            return;
        }
        this.state.error = null;
        this.state.tendered = String(this.state.order.total);
        this.state.view = "payment";
    }

    onTenderedInput(event) {
        this.state.tendered = event.target.value;
    }

    async confirmPayment() {
        if (this.state.busy) {
            return;
        }
        const received = Number(this.state.tendered);
        if (!this.state.tendered || !Number.isFinite(received) ||
            received < this.state.order.total) {
            this.state.error = "Cash received must cover the order total.";
            return;
        }
        this.state.busy = true;
        this.state.error = null;
        try {
            this.state.receipt = await this.orm.call(
                "restaurant.order", "pay_table_order", [[this.state.order.id], received]
            );
            this.state.view = "receipt";
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Payment could not be completed.";
        } finally {
            this.state.busy = false;
        }
    }

    itemImageUrl(item) {
        return `/web/image/restaurant.menu.item/${item.id}/image`;
    }

    floorStyle(floor) {
        const width = Math.max(960, ...floor.tables.map((table) => table.x + Math.max(72, table.width) / 2 + 36));
        const height = Math.max(680, ...floor.tables.map((table) => table.y + Math.max(72, table.height) / 2 + 36));
        const color = floor.background_color || "#f7f8fa";
        return `width:${width}px;height:${height}px;background-color:${color}`;
    }

    tableStyle(table) {
        const width = Math.max(72, table.width);
        const height = Math.max(72, table.height);
        return `left:${Math.max(8, table.x - width / 2)}px;top:${Math.max(8, table.y - height / 2)}px;width:${width}px;height:${height}px`;
    }

    formatMoney(amount, currency = this.state.currency) {
        return new Intl.NumberFormat(undefined, {
            style: "currency",
            currency,
        }).format(amount || 0);
    }
}

registry.category("actions").add("restaurant_pos.Tables", RestaurantTables);
