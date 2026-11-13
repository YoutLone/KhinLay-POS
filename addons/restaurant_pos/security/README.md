# Restaurant POS access policy

The Odoo 19 **Restaurant POS** privilege contains two groups. **Restaurant Admin**
implies **Restaurant Seller**, so administrators retain the seller workflow.
The groups, model ACLs, and expense record rules are loaded by the manifest.
Seller expenses are limited to their own records; Admin has an additional
all-expenses rule because the Admin group implies Seller.

| Model | Seller | Admin | Activation |
| --- | --- | --- | --- |
| Menu category, menu item | Read | Full CRUD | Phase 3 (active) |
| Order, order line | Read, create, write; no delete | Full CRUD | Phase 4 (active) |
| Ingredient | Read | Full CRUD | Phase 5 (active) |
| Recipe | Read | Full CRUD | Phase 5 (active) |
| Ingredient consumption | No access | Full CRUD | Phase 5 (active) |
| Expense | Read, create, write own; no delete | Full CRUD | Phase 6 (active) |
| Income and profit reports | No access | Read | Phase 7 (active) |

ACLs control model operations. The order model checks the Admin group inside
its cancellation method, because ACLs cannot restrict one state change.
Report actions, menus, and the dashboard require the Admin group. The expense model defaults
`purchased_by` to the current user and enforces it on seller creation; the
record rule limits seller read and write access to their own records.
