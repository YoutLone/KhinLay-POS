# Restaurant POS deployment

This setup runs Odoo 19 Community with PostgreSQL 16. Run the commands from
the repository root with Docker Compose installed. The local quickstart uses
an HTTP proxy; the production setup below uses an Nginx TLS proxy.

## Local UI quickstart

These commands use Docker Desktop and serve Odoo only on your computer at
`http://localhost:8069`. Run them from the repository root. The local Compose
override starts an HTTP proxy on port 8069 so the POS websocket reaches Odoo's
evented port. No TLS certificate is needed.

1. Copy the example environment file and replace both example passwords with
   your own values. Leave `ODOO_DB_NAME=restaurant_pos` for these commands.

   ```sh
   cp deploy/.env.example deploy/.env
   # Edit deploy/.env in your text editor.
   ```

2. Start PostgreSQL and install the module into a new database. This command
   also initializes Odoo's base data and loads the five demo menu items.

   ```sh
   docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml up -d db
   docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml run --rm odoo \
     odoo -d restaurant_pos -i restaurant_pos --stop-after-init
   ```

3. Start the web server and open `http://localhost:8069/web`.

   ```sh
   docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml up -d local_proxy
   ```

   Sign in with `admin` / `admin` on a fresh Odoo database, then change the
   administrator password. Assign your user the **Restaurant POS / Restaurant
   Admin** privilege in **Settings > Users & Companies > Users**. Sign out and
   back in if Point of Sale is not visible immediately.

   The login screen uses the main company logo. A new install starts with the
   sample Khin Lay logo. To replace it, go to **Settings > Users & Companies >
   Companies**, open the main company, click its logo image, upload your PNG or
   JPG, and save. Sign out or refresh `/web/login` to see the new logo. This
   company logo also appears elsewhere in Odoo, including reports. Module
   upgrades do not reset an uploaded logo.

   For an existing database that still shows Odoo's default logo, apply the
   sample once with:

   ```sh
   docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml \
     exec -T odoo sh -c 'odoo shell -d restaurant_pos --no-http --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" < /mnt/extra-addons/restaurant_pos/scripts/apply_sample_login_logo.py'
   ```

   The command leaves any logo you have already uploaded intact.

   If you replace `addons/restaurant_pos/static/img/sample_login_logo.png`
   after the database has been installed, update the stored company logo with:

   ```sh
   docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml \
     exec -T odoo sh -c 'odoo shell -d restaurant_pos --no-http --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" < /mnt/extra-addons/restaurant_pos/scripts/sync_login_logo.py'
   ```

   This replaces the main company's current logo, including one uploaded in
   Settings. Refresh `/web/login` to see the updated image.

4. Check the workflow in **Point of Sale > Restaurant**. Select **Open Register**
   or **Continue Selling**, choose a floor and table, add a menu product, and
   complete payment. Existing Main Floor and Patio layouts are reused. For
   recipes, open **Point of Sale > Restaurant Operations > Ingredients** and
   **Recipes** as a manager, then check **Daily Income** and **Profit and Loss**
   under the same Operations menu. A POS refund restores recipe ingredients.

The custom Restaurant POS app and its Quick Orders and Tables screens are
hidden. The addon remains installed for historical custom orders, ingredient
recipes, expenses, and combined reports. **Point of Sale > Restaurant
Operations > Legacy Custom Orders** gives managers read access to the old
order list. New sales should be entered only in the built-in register. Built-in
POS reports include POS orders; the extra Daily Income and Profit and Loss
reports also retain the old custom orders. Products created directly in POS
need a **Menu Product Links** record and recipe if ingredient deduction is
required. Existing linked products keep their recipes.

The backend uses OCA's free **Web Responsive** addon for the app menu and
smaller-screen layouts. Khin Lay colors are applied by the Restaurant POS
addon. The native POS register remains on Odoo's separate POS interface. The
vendored source and license are recorded in `addons/WEB_RESPONSIVE_SOURCE.md`.

Restaurant POS shows product photos on the menu cards after a table is selected.
Upload photos on POS products or under **Point of Sale > Restaurant Operations >
Menu Product Links**. A Menu Product Link photo is copied to its POS product.
The bundled sample photos can fill the current database's missing images without
replacing existing uploads:

```sh
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml \
  exec -T odoo sh -c 'odoo shell -d restaurant_pos --no-http --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" < /mnt/extra-addons/restaurant_pos/scripts/apply_sample_menu_images.py'
```

The photo credits are in `addons/restaurant_pos/static/img/menu/IMAGE_CREDITS.md`.
Reload the register after changing product images or its display setting.

For a database installed before the backend theme was added, install its
dependency and upgrade Restaurant POS once:

```sh
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml stop odoo
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml run --rm odoo \
  odoo -d restaurant_pos -i web_responsive -u restaurant_pos --stop-after-init
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml up -d odoo local_proxy
```

For an existing database, update the module after code changes with `-u`:

```sh
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml stop odoo
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml run --rm odoo \
  odoo -d restaurant_pos -u restaurant_pos --stop-after-init
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml up -d local_proxy
```

The module sets the main company's currency to MMK on a new installation.
The sample menu prices are also in MMK. New restaurant records and Odoo's
standard POS register use the company currency. An upgrade of an already
installed module does not change that company setting. Before changing an
existing company's currency, review its POS sales and accounting entries:
Odoo does not convert their recorded numbers when the currency label changes,
and individual transaction currency fields may still refer to the old
currency. Back up the database and plan a migration of those records if their
amounts were already entered in kyat. If they were entered in another
currency, retain or convert that history before using MMK for new sales.

For the existing Khin Lay database whose amounts were entered in kyat while
labeled USD, `deploy/migrate_existing_mmk.sql` performs that one-time relabeling.
It checks for a single USD company and rejects entries with exchange-rate
amounts. Stop Odoo and take a database backup before applying it. The script
does not convert numeric prices or amounts and cannot be run a second time.

To inspect startup logs or stop local services:

```sh
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml logs -f odoo
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.local.yml stop local_proxy odoo db
```

## Configure

For a server deployment, point a DNS record for the POS hostname to the server.

1. Copy `deploy/.env.example` to `deploy/.env`. Set long, different values for
   `POSTGRES_PASSWORD` and `ODOO_MASTER_PASSWORD`. Set `ODOO_DB_NAME` to the
   database name to serve. Keep this file private.
2. Replace `pos.example.com` in `deploy/nginx.conf` with your hostname.
3. Obtain a TLS certificate for that hostname. Put its full chain at
   `certs/fullchain.pem` and private key at `certs/privkey.pem`. Restrict access
   to the private key. Renew the certificate before expiry and restart Nginx.
4. Adjust `workers`, memory limits, and `max_cron_threads` in
   `deploy/odoo.conf` for the server. The Compose command applies the database
   filter `^ODOO_DB_NAME$`, so only the selected database is served.

## Start and install

```sh
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d db
docker compose --env-file deploy/.env -f deploy/docker-compose.yml run --rm odoo \
  odoo -d restaurant_pos -i restaurant_pos --stop-after-init
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d odoo nginx
```

Replace `restaurant_pos` in the install command if `ODOO_DB_NAME` differs. The
module is mounted from `addons/` into Odoo's extra addons path. Open the HTTPS
hostname and sign in as the Odoo database administrator. If the database is
already initialized, use `-u restaurant_pos` instead of `-i restaurant_pos`.

For PDF assets behind the proxy, set Odoo's `web.base.url` system parameter to
`https://pos.example.com` and `report.url` to `http://odoo:8069` (replace the
public hostname). The report URL is reachable from the Odoo container on the
Compose network.

In **Settings > Users**, create users for cashiers and managers. Give each an
internal user account and assign the **Restaurant POS / Restaurant Seller** or
**Restaurant POS / Restaurant Admin** privilege. Seller grants built-in POS
User; Admin grants POS Administrator. Set the company currency to MMK before
entering menu prices or stock costs. Configure recipes
and starting ingredient quantities before taking payments. Orders without a
recipe still sell, but do not consume ingredients.

## Backup

Back up both PostgreSQL and Odoo's filestore. Use matching timestamps for each
pair. These commands assume `ODOO_DB_NAME=restaurant_pos`:

```sh
mkdir -p backups
docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T db \
  pg_dump -U odoo -Fc restaurant_pos > backups/restaurant_pos.dump
docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T odoo \
  tar -czf - -C /var/lib/odoo/filestore restaurant_pos > backups/restaurant_pos-filestore.tar.gz
```

Copy backup files off the server and verify that they can be restored.

## Restore

Stop Odoo before replacing a database. The restore replaces the selected
database and filestore; use it only for a deliberate recovery.

```sh
docker compose --env-file deploy/.env -f deploy/docker-compose.yml stop odoo nginx
docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T db \
  dropdb -U odoo --if-exists restaurant_pos
docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T db \
  createdb -U odoo -O odoo restaurant_pos
docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T db \
  pg_restore -U odoo -d restaurant_pos < backups/restaurant_pos.dump
docker compose --env-file deploy/.env -f deploy/docker-compose.yml run --rm --no-deps \
  -v "$PWD/backups:/backup:ro" --entrypoint sh odoo -c \
  'mkdir -p /var/lib/odoo/filestore && tar -xzf /backup/restaurant_pos-filestore.tar.gz -C /var/lib/odoo/filestore'
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d odoo nginx
```

## Test a deployment

Before accepting orders, create a sample menu item, ingredient and recipe;
record a cash sale; verify ingredient quantity fell; add an expense; and compare
the daily income and profit report with the sample records. To run the module
tests against a separate database:

```sh
docker compose --env-file deploy/.env -f deploy/docker-compose.yml run --rm odoo \
  odoo -d restaurant_pos_test -i restaurant_pos --test-enable \
  --test-tags /restaurant_pos --stop-after-init
```

The PDF report requires Odoo's PDF renderer in the container. The official Odoo
image includes its runtime dependencies.
