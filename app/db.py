import logging

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models import Base

log = logging.getLogger("db")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _ensure_columns() -> None:
    """Idempotently add columns that exist in the ORM models but are missing
    from already-created tables.

    ``Base.metadata.create_all`` only creates missing *tables*; it never alters
    an existing table to add new *columns*. When the models gained columns such
    as ``gmail_accounts.last_sync_at`` / ``added_via`` after a database was first
    created, any query/insert referencing them raised
    ``OperationalError: no such column``. This lightweight, idempotent migration
    reconciles existing tables with the current models. It works on both SQLite
    and PostgreSQL (both support ``ALTER TABLE ... ADD COLUMN``).
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    dialect = engine.dialect
    preparer = dialect.identifier_preparer

    for table in Base.metadata.tables.values():
        if table.name not in existing_tables:
            # Brand-new table — create_all already handled it.
            continue
        db_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in db_columns:
                continue

            col_type = col.type.compile(dialect=dialect)
            ddl = f"ADD COLUMN {preparer.quote(col.name)} {col_type}"

            # Determine a usable scalar default so a NOT NULL column can be added
            # to a table that may already contain rows.
            scalar_default = (
                col.default is not None
                and getattr(col.default, "is_scalar", False)
            )
            if not col.nullable and scalar_default:
                ddl += f" DEFAULT {_sql_literal(col.default.arg)} NOT NULL"
            elif not col.nullable:
                # NOT NULL but no scalar default (e.g. created_at=datetime.utcnow).
                # Add as nullable to avoid failing on pre-existing rows. In practice
                # such columns are original and never appear in the missing set; this
                # is purely a safety net.
                log.warning(
                    "Column %s.%s is NOT NULL without a scalar default; "
                    "adding it as nullable to avoid migration failure.",
                    table.name, col.name,
                )

            stmt = f"ALTER TABLE {preparer.quote(table.name)} {ddl}"
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql(stmt)
                log.info("Schema migration: added column %s.%s", table.name, col.name)
            except Exception:
                log.exception("Schema migration failed for: %s", stmt)


def _sql_literal(value: object) -> str:
    """Render a Python scalar as a SQL literal for use in a DEFAULT clause."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    # Strings (and anything else) — single-quote and escape embedded quotes.
    return "'" + str(value).replace("'", "''") + "'"


def _ensure_indexes() -> None:
    """Idempotently create ORM-defined indexes missing from existing tables.

    ``create_all`` only creates missing tables; it never adds new indexes to
    tables that already exist. This reconciles existing databases with the
    current model definitions. Works on both SQLite and PostgreSQL.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.tables.values():
        if table.name not in existing_tables:
            continue
        existing_idx = {idx["name"] for idx in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name and index.name not in existing_idx:
                try:
                    index.create(engine)
                    log.info("Schema migration: created index %s on %s", index.name, table.name)
                except Exception:
                    log.exception("Schema migration: failed to create index %s", index.name)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_columns()
    _ensure_indexes()
