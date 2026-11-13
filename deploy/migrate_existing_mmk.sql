-- One-time migration for the existing Khin Lay database, where kyat amounts
-- were entered while the sole company and POS register were labeled USD.
-- Back up the database and stop Odoo before running this file.
\set ON_ERROR_STOP on
BEGIN;

DO $$
DECLARE
    usd_id integer;
    mmk_id integer;
BEGIN
    SELECT id INTO STRICT usd_id FROM res_currency WHERE name = 'USD';
    SELECT id INTO STRICT mmk_id FROM res_currency WHERE name = 'MMK';

    IF (SELECT COUNT(*) FROM res_company) <> 1
       OR (SELECT currency_id FROM res_company WHERE id = 1) <> usd_id THEN
        RAISE EXCEPTION 'Expected one company (id 1) with USD currency';
    END IF;
    IF EXISTS (
        SELECT 1 FROM account_move_line
        WHERE currency_id = usd_id AND amount_currency <> balance
    ) OR EXISTS (
        SELECT 1 FROM pos_order WHERE currency_rate <> 1
    ) THEN
        RAISE EXCEPTION 'Found exchange-rate amounts; review before relabeling';
    END IF;

    UPDATE res_currency
    SET active = true, symbol = 'MMK', position = 'after', write_date = now()
    WHERE id = mmk_id;
    UPDATE res_company SET currency_id = mmk_id WHERE id = 1;
    UPDATE pos_config SET currency_id = mmk_id WHERE currency_id = usd_id;

    UPDATE restaurant_menu_item SET currency_id = mmk_id WHERE currency_id = usd_id;
    UPDATE restaurant_ingredient SET currency_id = mmk_id WHERE currency_id = usd_id;
    UPDATE restaurant_order SET currency_id = mmk_id WHERE currency_id = usd_id;
    UPDATE restaurant_order SET company_currency_id = mmk_id
    WHERE company_currency_id = usd_id;
    UPDATE restaurant_order_line SET currency_id = mmk_id WHERE currency_id = usd_id;
    UPDATE restaurant_expense SET currency_id = mmk_id WHERE currency_id = usd_id;
    UPDATE restaurant_expense SET company_currency_id = mmk_id
    WHERE company_currency_id = usd_id;
    UPDATE restaurant_stock_move SET currency_id = mmk_id WHERE currency_id = usd_id;
    UPDATE restaurant_stock_move SET company_currency_id = mmk_id
    WHERE company_currency_id = usd_id;
    UPDATE restaurant_pos_consumption SET currency_id = mmk_id
    WHERE currency_id = usd_id;
    UPDATE restaurant_pos_consumption SET company_currency_id = mmk_id
    WHERE company_currency_id = usd_id;

    UPDATE account_move SET currency_id = mmk_id WHERE currency_id = usd_id;
    UPDATE account_move_line SET currency_id = mmk_id WHERE currency_id = usd_id;
    UPDATE account_move_line SET company_currency_id = mmk_id
    WHERE company_currency_id = usd_id;
    UPDATE account_bank_statement_line SET currency_id = mmk_id
    WHERE currency_id = usd_id;
    UPDATE account_partial_reconcile SET credit_currency_id = mmk_id
    WHERE credit_currency_id = usd_id;
    UPDATE account_partial_reconcile SET debit_currency_id = mmk_id
    WHERE debit_currency_id = usd_id;

    IF EXISTS (SELECT 1 FROM res_company WHERE currency_id <> mmk_id)
       OR EXISTS (SELECT 1 FROM pos_config WHERE currency_id <> mmk_id)
       OR EXISTS (SELECT 1 FROM account_move WHERE currency_id = usd_id)
       OR EXISTS (SELECT 1 FROM account_move_line
                  WHERE currency_id = usd_id OR company_currency_id = usd_id)
       OR EXISTS (SELECT 1 FROM restaurant_menu_item WHERE currency_id = usd_id)
       OR EXISTS (SELECT 1 FROM restaurant_ingredient WHERE currency_id = usd_id)
       OR EXISTS (SELECT 1 FROM restaurant_pos_consumption
                  WHERE currency_id = usd_id OR company_currency_id = usd_id) THEN
        RAISE EXCEPTION 'Currency migration left USD in a POS or ledger record';
    END IF;
END $$;

COMMIT;
