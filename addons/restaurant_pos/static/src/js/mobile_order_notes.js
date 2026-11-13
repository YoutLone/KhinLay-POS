import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { NoteButton } from "@point_of_sale/app/screens/product_screen/control_buttons/orderline_note_button/orderline_note_button";

ProductScreen.components = {
    ...ProductScreen.components,
    NoteButton,
};
