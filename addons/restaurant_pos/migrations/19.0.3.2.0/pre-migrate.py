"""Give historical single-amount expenses a quantity of one."""


def migrate(cr, version):
    cr.execute("ALTER TABLE restaurant_expense ADD COLUMN IF NOT EXISTS quantity double precision")
    cr.execute("UPDATE restaurant_expense SET quantity = 1 WHERE quantity IS NULL")
