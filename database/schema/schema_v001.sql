-- ============================================================================
-- MAZANDASHT — Schema v001 (initial)
-- Stack: SQLite x64 (local, transactional). Money = INTEGER Rial.
-- Weight base = INTEGER grams. Dates stored ISO; Shamsi kept as entered text.
-- Every table has a stable internal id; business codes are separate UNIQUE
-- columns so display-name changes never break history (Spec ch. 4.2).
-- ============================================================================
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ---------------------------------------------------------------------------
-- System / migration bookkeeping
-- ---------------------------------------------------------------------------
CREATE TABLE schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    checksum    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE company_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE sequences (
    name        TEXT PRIMARY KEY,          -- e.g. 'weigh_ticket', 'journal'
    prefix      TEXT NOT NULL DEFAULT '',
    next_number INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE fiscal_periods (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    start_date  TEXT NOT NULL,             -- ISO date
    end_date    TEXT NOT NULL,             -- ISO date
    is_closed   INTEGER NOT NULL DEFAULT 0 CHECK (is_closed IN (0,1)),
    UNIQUE (title)
);

CREATE TABLE audit_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id),
    action      TEXT NOT NULL,             -- CREATE/UPDATE/APPROVE/VOID/LOGIN/...
    entity_type TEXT NOT NULL,
    entity_id   INTEGER,
    details     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_audit_entity ON audit_events(entity_type, entity_id);

-- ---------------------------------------------------------------------------
-- Users / roles / permissions / keys (Spec ch. 10)
-- ---------------------------------------------------------------------------
CREATE TABLE roles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,      -- ADMIN / MANAGER / OPERATOR
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE permissions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,      -- e.g. 'weigh.create'
    name        TEXT NOT NULL
);

CREATE TABLE role_permissions (
    role_id       INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    role_id       INTEGER NOT NULL REFERENCES roles(id),
    password_hash TEXT NOT NULL,           -- PBKDF2-HMAC-SHA256, never plaintext
    password_salt TEXT NOT NULL,           -- independent salt per user
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT
);

CREATE TABLE user_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash    TEXT NOT NULL,             -- hash of the 32-byte private key
    key_prefix  TEXT NOT NULL DEFAULT '',  -- first chars, for identification
    is_revoked  INTEGER NOT NULL DEFAULT 0 CHECK (is_revoked IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at  TEXT,
    expires_at  TEXT
);
CREATE INDEX ix_user_keys_user ON user_keys(user_id);

-- ---------------------------------------------------------------------------
-- Reference data (INFO.xlsx) — codes per Spec ch. 4.2
-- ---------------------------------------------------------------------------
CREATE TABLE account_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,             -- مشتری، فروشنده، ... (Groups sheet)
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE main_groups (                 -- G prefix
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE sub_groups (                  -- SG prefix
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    main_group_id INTEGER NOT NULL REFERENCES main_groups(id),
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE work_groups (                 -- WG prefix
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE parties (                     -- Accounts sheet; C/SL/S/E/X/F/L/CAP
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    code              TEXT NOT NULL UNIQUE,  -- stable system code (e.g. S001)
    display_name      TEXT NOT NULL,         -- changeable; never breaks history
    nature            TEXT NOT NULL CHECK (nature IN ('C','SL','S','E','X','F','L','CAP')),
    national_code     TEXT NOT NULL DEFAULT '',
    phone             TEXT NOT NULL DEFAULT '',
    mobile            TEXT NOT NULL DEFAULT '',
    address           TEXT NOT NULL DEFAULT '',
    accounting_group_id INTEGER REFERENCES account_groups(id),
    audit_group_id      INTEGER REFERENCES account_groups(id),
    is_active         INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_parties_nature ON parties(nature);

CREATE TABLE party_roles (                 -- one party, many business roles
    party_id INTEGER NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
    role     TEXT NOT NULL CHECK (role IN ('CUSTOMER','SUPPLIER','VENDOR','EMPLOYEE','OTHER')),
    PRIMARY KEY (party_id, role)
);

CREATE TABLE staff (                       -- Staff sheet; E prefix via parties
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    party_id      INTEGER NOT NULL REFERENCES parties(id),
    work_group_id INTEGER REFERENCES work_groups(id),
    position      TEXT NOT NULL DEFAULT '',
    card_number   TEXT NOT NULL DEFAULT '',
    sheba         TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE banks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE bank_accounts (               -- BANK prefix; Banks sheet
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    code                  TEXT NOT NULL UNIQUE,   -- BANK01, BANK02, ...
    bank_id               INTEGER REFERENCES banks(id),
    display_name          TEXT NOT NULL,          -- عنوان نمایشی روزمره
    account_number        TEXT NOT NULL DEFAULT '',
    sheba                 TEXT NOT NULL DEFAULT '',
    opening_balance_rial  INTEGER NOT NULL DEFAULT 0 CHECK (typeof(opening_balance_rial)='integer'),
    is_active             INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    description           TEXT NOT NULL DEFAULT ''
);

CREATE TABLE cheques_registry (            -- Cheques sheet (reference data)
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cheque_number TEXT NOT NULL,
    bank_id       INTEGER REFERENCES banks(id),
    branch        TEXT NOT NULL DEFAULT '',
    booklet_number TEXT NOT NULL DEFAULT '',
    series        TEXT NOT NULL DEFAULT '',
    serial        TEXT NOT NULL DEFAULT '',
    sayad_id      TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE txn_types (                   -- T prefix; colors per Spec ch. 12
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,          -- واریز، برداشت، کارمزد، انتقال، پاس چک، وصول چک
    effect_on_balance TEXT NOT NULL DEFAULT '',  -- افزایش / کاهش
    color_hex       TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE operation_types (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE operations (                  -- OP prefix; Ops sheet
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    direction     TEXT NOT NULL CHECK (direction IN ('IN','OUT')),
    main_group_id INTEGER REFERENCES main_groups(id),
    description   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE units (                       -- Lists sheet: واحد شمارش
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,              -- گرم، کیلوگرم، عدد، سبد، کارتن، ...
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE product_groups (              -- hierarchical product tree (ch. 4.3)
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    parent_id   INTEGER REFERENCES product_groups(id),
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE products (                    -- PB (buy) / PS (sell) prefixes
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    group_id    INTEGER REFERENCES product_groups(id),
    name        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT '',
    unit_id     INTEGER REFERENCES units(id),
    is_buy      INTEGER NOT NULL DEFAULT 0 CHECK (is_buy IN (0,1)),
    is_sell     INTEGER NOT NULL DEFAULT 0 CHECK (is_sell IN (0,1)),
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE grades (                      -- درجه یک/دو/سه/ضایعات (optional per product)
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE packaging_types (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,              -- سبد، کارتن، کیسه، جعبه
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE baskets (                     -- BK prefix; Baskets sheet
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,     -- BK01
    name          TEXT NOT NULL,            -- سبد ۵ کیلویی
    capacity_grams INTEGER NOT NULL DEFAULT 0 CHECK (typeof(capacity_grams)='integer'),
    description   TEXT NOT NULL DEFAULT '',
    auto_label    INTEGER NOT NULL DEFAULT 0 CHECK (auto_label IN (0,1))
);

CREATE TABLE warehouses (                  -- W prefix; Warehouses sheet
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    location       TEXT NOT NULL DEFAULT '',
    keeper_party_id INTEGER REFERENCES parties(id),
    description    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE parameters (                  -- P prefix; Params sheet
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,     -- P01, P02, ...
    name          TEXT NOT NULL,
    value_text    TEXT NOT NULL DEFAULT '',
    value_number  REAL,
    unit          TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    is_confirmed  INTEGER NOT NULL DEFAULT 0 CHECK (is_confirmed IN (0,1))
);

-- ---------------------------------------------------------------------------
-- Operational documents (approval: DRAFT / REVIEW / APPROVED / VOIDED)
-- ---------------------------------------------------------------------------
CREATE TABLE weigh_tickets (               -- Baskol.xlsx
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    code              TEXT NOT NULL UNIQUE,
    doc_number        TEXT NOT NULL DEFAULT '',   -- display number, independent of id
    date_iso          TEXT NOT NULL DEFAULT '',
    date_shamsi       TEXT NOT NULL DEFAULT '',
    time              TEXT NOT NULL DEFAULT '',
    operation_id      INTEGER REFERENCES operations(id),
    direction         TEXT NOT NULL CHECK (direction IN ('IN','OUT')),
    party_id          INTEGER REFERENCES parties(id),
    sub_group_id      INTEGER REFERENCES sub_groups(id),
    product_id        INTEGER REFERENCES products(id),
    gross_kg_raw      TEXT NOT NULL DEFAULT '',   -- raw input, traceable
    gross_grams       INTEGER NOT NULL DEFAULT 0 CHECK (typeof(gross_grams)='integer'),
    tare_grams        INTEGER NOT NULL DEFAULT 0 CHECK (typeof(tare_grams)='integer'),
    loss_grams        INTEGER NOT NULL DEFAULT 0 CHECK (typeof(loss_grams)='integer'),
    net_grams         INTEGER NOT NULL DEFAULT 0 CHECK (typeof(net_grams)='integer'),
    basket_count      INTEGER NOT NULL DEFAULT 0,
    basket_id         INTEGER REFERENCES baskets(id),
    amount_rial       INTEGER NOT NULL DEFAULT 0 CHECK (typeof(amount_rial)='integer'),
    status            TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    void_reason       TEXT NOT NULL DEFAULT '',
    param_snapshot    TEXT NOT NULL DEFAULT '',   -- effective params at registration (JSON)
    created_by        INTEGER REFERENCES users(id),
    approved_by       INTEGER REFERENCES users(id),
    description       TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_weigh_status ON weigh_tickets(status);
CREATE INDEX ix_weigh_party  ON weigh_tickets(party_id);

CREATE TABLE lots (                        -- محموله / Lot
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    weigh_ticket_id INTEGER REFERENCES weigh_tickets(id),
    product_id     INTEGER REFERENCES products(id),
    grade_id       INTEGER REFERENCES grades(id),
    packaging_id   INTEGER REFERENCES packaging_types(id),
    warehouse_id   INTEGER REFERENCES warehouses(id),
    quantity_grams INTEGER NOT NULL DEFAULT 0 CHECK (typeof(quantity_grams)='integer'),
    status         TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED'))
);

CREATE TABLE sorting_batches (             -- Spec ch. 8
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    code               TEXT NOT NULL UNIQUE,
    lot_id             INTEGER REFERENCES lots(id),
    input_grams        INTEGER NOT NULL DEFAULT 0 CHECK (typeof(input_grams)='integer'),
    output_grams       INTEGER NOT NULL DEFAULT 0 CHECK (typeof(output_grams)='integer'),
    waste_grams        INTEGER NOT NULL DEFAULT 0 CHECK (typeof(waste_grams)='integer'),
    process_loss_grams INTEGER NOT NULL DEFAULT 0 CHECK (typeof(process_loss_grams)='integer'),
    variance_grams     INTEGER NOT NULL DEFAULT 0 CHECK (typeof(variance_grams)='integer'),
    tolerance_grams    INTEGER NOT NULL DEFAULT 0 CHECK (typeof(tolerance_grams)='integer'),
    status             TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    created_by         INTEGER REFERENCES users(id),
    approved_by        INTEGER REFERENCES users(id),
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sorting_inputs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES sorting_batches(id) ON DELETE CASCADE,
    lot_id   INTEGER REFERENCES lots(id),
    grams    INTEGER NOT NULL DEFAULT 0 CHECK (typeof(grams)='integer')
);

CREATE TABLE sorting_outputs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id     INTEGER NOT NULL REFERENCES sorting_batches(id) ON DELETE CASCADE,
    product_id   INTEGER REFERENCES products(id),
    grade_id     INTEGER REFERENCES grades(id),
    packaging_id INTEGER REFERENCES packaging_types(id),
    warehouse_id INTEGER REFERENCES warehouses(id),
    grams        INTEGER NOT NULL DEFAULT 0 CHECK (typeof(grams)='integer'),
    package_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE waste_records (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER REFERENCES sorting_batches(id) ON DELETE CASCADE,
    grams    INTEGER NOT NULL DEFAULT 0 CHECK (typeof(grams)='integer'),
    reason   TEXT NOT NULL DEFAULT ''
);

-- Append-only stock ledger. Balances are DERIVED (SUM); no balance column
-- exists, so direct balance editing is impossible by design (Spec ch. 8).
CREATE TABLE stock_movements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id        INTEGER REFERENCES lots(id),
    product_id    INTEGER REFERENCES products(id),
    grade_id      INTEGER REFERENCES grades(id),
    packaging_id  INTEGER REFERENCES packaging_types(id),
    warehouse_id  INTEGER REFERENCES warehouses(id),
    movement_type TEXT NOT NULL CHECK (movement_type IN ('IN','OUT','ADJUST')),
    quantity_grams INTEGER NOT NULL CHECK (typeof(quantity_grams)='integer'),
    quantity_count INTEGER NOT NULL DEFAULT 0,
    ref_type      TEXT NOT NULL DEFAULT '',   -- weigh_ticket / sorting_batch / sales_invoice / ...
    ref_id        INTEGER,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_stock_key ON stock_movements(product_id, grade_id, packaging_id, warehouse_id, lot_id);

CREATE TABLE purchase_invoices (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    doc_number     TEXT NOT NULL DEFAULT '',
    date_iso       TEXT NOT NULL DEFAULT '',
    date_shamsi    TEXT NOT NULL DEFAULT '',
    party_id       INTEGER REFERENCES parties(id),
    weigh_ticket_id INTEGER REFERENCES weigh_tickets(id),
    lot_id         INTEGER REFERENCES lots(id),
    status         TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    void_reason    TEXT NOT NULL DEFAULT '',
    created_by     INTEGER REFERENCES users(id),
    approved_by    INTEGER REFERENCES users(id),
    description    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE purchase_invoice_lines (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id     INTEGER NOT NULL REFERENCES purchase_invoices(id) ON DELETE CASCADE,
    product_id     INTEGER REFERENCES products(id),
    grams          INTEGER NOT NULL DEFAULT 0 CHECK (typeof(grams)='integer'),
    rate_rial_per_kg INTEGER NOT NULL DEFAULT 0 CHECK (typeof(rate_rial_per_kg)='integer'),
    gross_rial     INTEGER NOT NULL DEFAULT 0 CHECK (typeof(gross_rial)='integer'),
    discount_rial  INTEGER NOT NULL DEFAULT 0 CHECK (typeof(discount_rial)='integer'),
    freight_rial   INTEGER NOT NULL DEFAULT 0 CHECK (typeof(freight_rial)='integer'),
    commission_rial INTEGER NOT NULL DEFAULT 0 CHECK (typeof(commission_rial)='integer'),
    adjustments_rial INTEGER NOT NULL DEFAULT 0 CHECK (typeof(adjustments_rial)='integer'),
    net_rial       INTEGER NOT NULL DEFAULT 0 CHECK (typeof(net_rial)='integer')
);

CREATE TABLE sales_invoices (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    doc_number     TEXT NOT NULL DEFAULT '',
    date_iso       TEXT NOT NULL DEFAULT '',
    date_shamsi    TEXT NOT NULL DEFAULT '',
    party_id       INTEGER REFERENCES parties(id),
    lot_id         INTEGER REFERENCES lots(id),
    sorting_batch_id INTEGER REFERENCES sorting_batches(id),
    status         TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    void_reason    TEXT NOT NULL DEFAULT '',
    created_by     INTEGER REFERENCES users(id),
    approved_by    INTEGER REFERENCES users(id),
    description    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sales_invoice_lines (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id     INTEGER NOT NULL REFERENCES sales_invoices(id) ON DELETE CASCADE,
    product_id     INTEGER REFERENCES products(id),
    grade_id       INTEGER REFERENCES grades(id),
    packaging_id   INTEGER REFERENCES packaging_types(id),
    grams          INTEGER NOT NULL DEFAULT 0 CHECK (typeof(grams)='integer'),
    rate_rial_per_kg INTEGER NOT NULL DEFAULT 0 CHECK (typeof(rate_rial_per_kg)='integer'),
    gross_rial     INTEGER NOT NULL DEFAULT 0 CHECK (typeof(gross_rial)='integer'),
    discount_rial  INTEGER NOT NULL DEFAULT 0 CHECK (typeof(discount_rial)='integer'),
    freight_rial   INTEGER NOT NULL DEFAULT 0 CHECK (typeof(freight_rial)='integer'),
    commission_rial INTEGER NOT NULL DEFAULT 0 CHECK (typeof(commission_rial)='integer'),
    other_costs_rial INTEGER NOT NULL DEFAULT 0 CHECK (typeof(other_costs_rial)='integer'),
    net_rial       INTEGER NOT NULL DEFAULT 0 CHECK (typeof(net_rial)='integer')
);

CREATE TABLE payments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    party_id       INTEGER REFERENCES parties(id),
    bank_account_id INTEGER REFERENCES bank_accounts(id),
    txn_type_id    INTEGER REFERENCES txn_types(id),
    direction      TEXT NOT NULL CHECK (direction IN ('IN','OUT')),
    amount_rial    INTEGER NOT NULL DEFAULT 0 CHECK (typeof(amount_rial)='integer'),
    date_iso      TEXT NOT NULL DEFAULT '',
    date_shamsi    TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    void_reason    TEXT NOT NULL DEFAULT '',
    created_by     INTEGER REFERENCES users(id),
    approved_by    INTEGER REFERENCES users(id),
    description    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE payment_allocations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    invoice_id INTEGER NOT NULL,              -- purchase or sales invoice id
    invoice_kind TEXT NOT NULL CHECK (invoice_kind IN ('PURCHASE','SALES')),
    amount_rial INTEGER NOT NULL DEFAULT 0 CHECK (typeof(amount_rial)='integer')
);

CREATE TABLE bank_transactions (           -- Transactions.xlsx Entry (single engine)
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    code               TEXT NOT NULL UNIQUE,
    bank_account_id    INTEGER NOT NULL REFERENCES bank_accounts(id),
    party_id           INTEGER REFERENCES parties(id),
    txn_type_id        INTEGER REFERENCES txn_types(id),
    main_group_id      INTEGER REFERENCES main_groups(id),
    sub_group_id       INTEGER REFERENCES sub_groups(id),
    date_iso          TEXT NOT NULL DEFAULT '',
    date_shamsi        TEXT NOT NULL DEFAULT '',
    time               TEXT NOT NULL DEFAULT '',
    deposit_rial       INTEGER NOT NULL DEFAULT 0 CHECK (typeof(deposit_rial)='integer'),
    withdrawal_rial    INTEGER NOT NULL DEFAULT 0 CHECK (typeof(withdrawal_rial)='integer'),
    bank_balance_rial  INTEGER NOT NULL DEFAULT 0 CHECK (typeof(bank_balance_rial)='integer'),
    system_balance_rial INTEGER NOT NULL DEFAULT 0 CHECK (typeof(system_balance_rial)='integer'),
    status             TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    void_reason        TEXT NOT NULL DEFAULT '',
    cheque_number      TEXT NOT NULL DEFAULT '',
    source_key         TEXT NOT NULL DEFAULT '',   -- idempotency key (duplicate control)
    description        TEXT NOT NULL DEFAULT '',
    created_by         INTEGER REFERENCES users(id),
    approved_by        INTEGER REFERENCES users(id),
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX ux_bank_source_key ON bank_transactions(source_key) WHERE source_key <> '';
CREATE INDEX ix_bank_account ON bank_transactions(bank_account_id, date_iso);

CREATE TABLE cheques (                     -- Cheques.xlsx; ISSUED and RECEIVED are independent flows
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    code               TEXT NOT NULL UNIQUE,
    cheque_number      TEXT NOT NULL,
    bank_account_id    INTEGER REFERENCES bank_accounts(id),
    cheque_date        TEXT NOT NULL DEFAULT '',
    amount_rial        INTEGER NOT NULL DEFAULT 0 CHECK (typeof(amount_rial)='integer'),
    beneficiary_party_id INTEGER REFERENCES parties(id),
    direction          TEXT NOT NULL CHECK (direction IN ('ISSUED','RECEIVED')),
    status             TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','PAID','COLLECTED','RETURNED','VOIDED')),
    paid_date          TEXT NOT NULL DEFAULT '',
    description        TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE cheque_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cheque_id  INTEGER NOT NULL REFERENCES cheques(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,               -- ISSUE/RECEIVE/PAID/COLLECT/RETURN
    event_date TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE basket_movements (            -- Baskets.xlsx; independent from money flow
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    basket_id      INTEGER NOT NULL REFERENCES baskets(id),
    party_id       INTEGER REFERENCES parties(id),
    event_type     TEXT NOT NULL CHECK (event_type IN ('RECEIVE','ISSUE','RETURN','PURCHASE')),
    quantity       INTEGER NOT NULL DEFAULT 0,
    rate_rial      INTEGER NOT NULL DEFAULT 0 CHECK (typeof(rate_rial)='integer'),
    amount_rial    INTEGER NOT NULL DEFAULT 0 CHECK (typeof(amount_rial)='integer'),
    balance_rial   INTEGER NOT NULL DEFAULT 0 CHECK (typeof(balance_rial)='integer'),
    date_iso      TEXT NOT NULL DEFAULT '',
    date_shamsi    TEXT NOT NULL DEFAULT '',
    doc_number     TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Partnership (Spec ch. 6): consumed baskets and returned custody baskets
-- are separate fields and must never be merged.
CREATE TABLE partnerships (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    partner_party_id INTEGER REFERENCES parties(id),
    description    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE partnership_events (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    partnership_id         INTEGER NOT NULL REFERENCES partnerships(id) ON DELETE CASCADE,
    event_type             TEXT NOT NULL,   -- PURCHASE_AGGREGATION / LOAD_IN / LOAD_OUT / COLD_STORE / SETTLEMENT / ...
    date_shamsi            TEXT NOT NULL DEFAULT '',
    party_id               INTEGER REFERENCES parties(id),
    load_type              TEXT NOT NULL DEFAULT '',
    basket_type            TEXT NOT NULL DEFAULT '',
    basket_count           INTEGER NOT NULL DEFAULT 0,   -- consumed baskets
    returned_basket_count  INTEGER NOT NULL DEFAULT 0,   -- returned custody baskets (separate!)
    weigh_grams            INTEGER NOT NULL DEFAULT 0 CHECK (typeof(weigh_grams)='integer'),
    net_grams              INTEGER NOT NULL DEFAULT 0 CHECK (typeof(net_grams)='integer'),
    rounding_mode          TEXT NOT NULL DEFAULT '',
    manual_loss_grams      INTEGER NOT NULL DEFAULT 0 CHECK (typeof(manual_loss_grams)='integer'),
    extra_waste_grams      INTEGER NOT NULL DEFAULT 0 CHECK (typeof(extra_waste_grams)='integer'),
    purchase_code          TEXT NOT NULL DEFAULT '',
    receipt_number         TEXT NOT NULL DEFAULT '',
    partner_share_grams    INTEGER NOT NULL DEFAULT 0 CHECK (typeof(partner_share_grams)='integer'),
    our_share_grams        INTEGER NOT NULL DEFAULT 0 CHECK (typeof(our_share_grams)='integer'),
    loss_percent           REAL,
    basket_total_grams     INTEGER NOT NULL DEFAULT 0 CHECK (typeof(basket_total_grams)='integer'),
    after_tare_grams       INTEGER NOT NULL DEFAULT 0 CHECK (typeof(after_tare_grams)='integer'),
    loss_grams             INTEGER NOT NULL DEFAULT 0 CHECK (typeof(loss_grams)='integer'),
    net_before_rounding_grams INTEGER NOT NULL DEFAULT 0 CHECK (typeof(net_before_rounding_grams)='integer'),
    suggested_purchase_code TEXT NOT NULL DEFAULT '',
    stock_effect           TEXT NOT NULL DEFAULT '',
    basket_custody_effect  TEXT NOT NULL DEFAULT '',
    warning                TEXT NOT NULL DEFAULT '',
    created_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE purchase_aggregations (       -- تجمیع خرید (Spec ch. 6)
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT NOT NULL UNIQUE,
    party_id            INTEGER REFERENCES parties(id),
    load_type           TEXT NOT NULL DEFAULT '',
    row_count           INTEGER NOT NULL DEFAULT 0,
    weigh_total_grams   INTEGER NOT NULL DEFAULT 0 CHECK (typeof(weigh_total_grams)='integer'),
    net_total_grams     INTEGER NOT NULL DEFAULT 0 CHECK (typeof(net_total_grams)='integer'),
    basket_count        INTEGER NOT NULL DEFAULT 0,
    buy_rate_rial       INTEGER NOT NULL DEFAULT 0 CHECK (typeof(buy_rate_rial)='integer'),
    base_amount_rial    INTEGER NOT NULL DEFAULT 0 CHECK (typeof(base_amount_rial)='integer'),
    agreed_discount_rial INTEGER NOT NULL DEFAULT 0 CHECK (typeof(agreed_discount_rial)='integer'),
    final_agreed_rial   INTEGER NOT NULL DEFAULT 0 CHECK (typeof(final_agreed_rial)='integer'),
    paid_rial           INTEGER NOT NULL DEFAULT 0 CHECK (typeof(paid_rial)='integer'),
    payment_difference_rial INTEGER NOT NULL DEFAULT 0 CHECK (typeof(payment_difference_rial)='integer'),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE employee_wages (              -- Employees.xlsx Wages
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    date_iso       TEXT NOT NULL DEFAULT '',
    date_shamsi     TEXT NOT NULL DEFAULT '',
    wage_type       TEXT NOT NULL DEFAULT '',
    party_id        INTEGER REFERENCES parties(id),
    total_rial      INTEGER NOT NULL DEFAULT 0 CHECK (typeof(total_rial)='integer'),
    shares_total_rial INTEGER NOT NULL DEFAULT 0 CHECK (typeof(shares_total_rial)='integer'),
    status          TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    description     TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE wage_shares (                 -- Employees.xlsx Shares; SUM must equal wage total
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    wage_id        INTEGER NOT NULL REFERENCES employee_wages(id) ON DELETE CASCADE,
    member_party_id INTEGER REFERENCES parties(id),
    share_rial     INTEGER NOT NULL DEFAULT 0 CHECK (typeof(share_rial)='integer'),
    description    TEXT NOT NULL DEFAULT ''
);

-- ---------------------------------------------------------------------------
-- Double-entry accounting (Spec ch. 9). Posting is atomic and idempotent via
-- source_key. Approved entries are immutable (triggers below).
-- ---------------------------------------------------------------------------
CREATE TABLE accounts (                    -- chart of accounts for journal lines
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN ('ASSET','LIABILITY','EQUITY','INCOME','EXPENSE')),
    group_id    INTEGER REFERENCES account_groups(id),
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
);

CREATE TABLE journal_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    doc_number  TEXT NOT NULL DEFAULT '',
    date_iso    TEXT NOT NULL DEFAULT '',
    date_shamsi TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    void_reason TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',   -- purchase_invoice / sales_invoice / payment / ...
    source_id   INTEGER,
    source_key  TEXT NOT NULL DEFAULT '',   -- idempotency: one posting per source
    created_by  INTEGER REFERENCES users(id),
    approved_by INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX ux_journal_source_key ON journal_entries(source_key) WHERE source_key <> '';

CREATE TABLE journal_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id  INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    debit_rial  INTEGER NOT NULL DEFAULT 0 CHECK (typeof(debit_rial)='integer' AND debit_rial >= 0),
    credit_rial INTEGER NOT NULL DEFAULT 0 CHECK (typeof(credit_rial)='integer' AND credit_rial >= 0),
    description TEXT NOT NULL DEFAULT '',
    CHECK (debit_rial = 0 OR credit_rial = 0)   -- a line is debit XOR credit
);

-- Immutability of approved journal entries: no UPDATE/DELETE after APPROVED.
-- NOTE (Reset, Spec ch. 15): database Reset is implemented by replacing the
-- DB file (mandatory backup -> archive -> fresh DB from schema+seed), never
-- by deleting rows, so these triggers stay intact.
CREATE TRIGGER trg_journal_no_update_approved
BEFORE UPDATE ON journal_entries
WHEN OLD.status = 'APPROVED'
BEGIN
    SELECT RAISE(ABORT, 'Approved journal entries are immutable; use a reversal entry.');
END;

CREATE TRIGGER trg_journal_no_delete_approved
BEFORE DELETE ON journal_entries
WHEN OLD.status = 'APPROVED'
BEGIN
    SELECT RAISE(ABORT, 'Approved journal entries cannot be deleted; use a reversal entry.');
END;

CREATE TRIGGER trg_journal_line_no_update_approved
BEFORE UPDATE ON journal_lines
WHEN (SELECT status FROM journal_entries WHERE id = OLD.journal_id) = 'APPROVED'
BEGIN
    SELECT RAISE(ABORT, 'Lines of an approved journal entry are immutable.');
END;

CREATE TRIGGER trg_journal_line_no_delete_approved
BEFORE DELETE ON journal_lines
WHEN (SELECT status FROM journal_entries WHERE id = OLD.journal_id) = 'APPROVED'
BEGIN
    SELECT RAISE(ABORT, 'Lines of an approved journal entry cannot be deleted.');
END;

-- ---------------------------------------------------------------------------
-- Import / Export / Backup (Spec ch. 14, 16)
-- ---------------------------------------------------------------------------
CREATE TABLE import_batches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    file_name     TEXT NOT NULL DEFAULT '',
    file_type     TEXT NOT NULL DEFAULT '',   -- XLSX / CSV
    detected_type TEXT NOT NULL DEFAULT '',
    header_row    INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED','ROLLED_BACK')),
    total_rows    INTEGER NOT NULL DEFAULT 0,
    valid_rows    INTEGER NOT NULL DEFAULT 0,
    duplicate_rows INTEGER NOT NULL DEFAULT 0,
    invalid_rows  INTEGER NOT NULL DEFAULT 0,
    created_by    INTEGER REFERENCES users(id),
    approved_by   INTEGER REFERENCES users(id),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE import_rows (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    row_number  INTEGER NOT NULL DEFAULT 0,
    raw_json    TEXT NOT NULL DEFAULT '',
    mapped_json TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','VALID','DUPLICATE','INVALID','IMPORTED','SKIPPED')),
    error_message TEXT NOT NULL DEFAULT ''
);

CREATE TABLE import_profiles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    target_type TEXT NOT NULL DEFAULT '',
    mapping_json TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE export_jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    export_type TEXT NOT NULL DEFAULT '',
    format      TEXT NOT NULL DEFAULT '',   -- XLSX / CSV / PDF
    file_name   TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'DRAFT',
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE backup_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    backup_type     TEXT NOT NULL CHECK (backup_type IN ('EXIT','BEFORE_SENSITIVE','BEFORE_MIGRATION','BEFORE_RESET','MANUAL','SCHEDULED')),
    file_path       TEXT NOT NULL DEFAULT '',
    sha256          TEXT NOT NULL DEFAULT '',
    schema_version  INTEGER NOT NULL DEFAULT 0,
    integrity_result TEXT NOT NULL DEFAULT '',
    manifest_json   TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'DRAFT',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Reporting views (all derived from real posted data — no mock values)
-- ---------------------------------------------------------------------------
CREATE VIEW v_journal_balance AS
SELECT je.id AS journal_id, je.code, je.status,
       COALESCE(SUM(jl.debit_rial),0)  AS total_debit,
       COALESCE(SUM(jl.credit_rial),0) AS total_credit,
       COALESCE(SUM(jl.debit_rial),0) - COALESCE(SUM(jl.credit_rial),0) AS difference
FROM journal_entries je
LEFT JOIN journal_lines jl ON jl.journal_id = je.id
GROUP BY je.id;

CREATE VIEW v_stock_balance AS
SELECT product_id, grade_id, packaging_id, warehouse_id, lot_id,
       SUM(CASE WHEN movement_type='IN' THEN quantity_grams
                WHEN movement_type='OUT' THEN -quantity_grams
                ELSE quantity_grams END) AS balance_grams,
       SUM(CASE WHEN movement_type='IN' THEN quantity_count
                WHEN movement_type='OUT' THEN -quantity_count
                ELSE quantity_count END) AS balance_count
FROM stock_movements
GROUP BY product_id, grade_id, packaging_id, warehouse_id, lot_id;

CREATE VIEW v_account_balance AS
SELECT a.id AS account_id, a.code, a.title, a.account_type,
       COALESCE(SUM(jl.debit_rial),0)  AS total_debit,
       COALESCE(SUM(jl.credit_rial),0) AS total_credit,
       COALESCE(SUM(jl.debit_rial),0) - COALESCE(SUM(jl.credit_rial),0) AS balance_rial
FROM accounts a
LEFT JOIN journal_lines jl ON jl.account_id = a.id
LEFT JOIN journal_entries je ON je.id = jl.journal_id AND je.status = 'APPROVED'
GROUP BY a.id;
