from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from src.config.configs import settings
from src.database.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# ------------------------------------------------------------------
# Use a sync DB URL for Alembic when the application uses asyncpg
# Alembic (and many DB API drivers) expect a synchronous DBAPI during
# migrations. If your app's DATABASE_URL uses the asyncpg driver
# (postgresql+asyncpg://...), replace it with a sync driver for
# migrations (postgresql+psycopg2://...). Installing psycopg[binary]
# locally is recommended for running migrations from the host.
# ------------------------------------------------------------------
raw_db_url = None
try:
    # settings.database.DATABASE_URL is a SecretStr in the project's config
    raw_db_url = settings.database.DATABASE_URL.get_secret_value()
except Exception:
    # Fallback if it's a plain string
    raw_db_url = str(getattr(settings.database, "DATABASE_URL", ""))

# If the URL uses asyncpg, switch to psycopg2 for Alembic operations.
if raw_db_url and "+asyncpg" in raw_db_url:
    sync_db_url = raw_db_url.replace("+asyncpg", "+psycopg2")
else:
    sync_db_url = raw_db_url

# Set the database URL for Alembic
if sync_db_url:
    config.set_main_option("sqlalchemy.url", sync_db_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
