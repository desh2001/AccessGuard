"""Schema upgrades for pre-existing Aegis V5 databases."""
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.db import Base
from app import models  # noqa: F401; registers metadata
import os

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
url=os.environ.get('DATABASE_URL','sqlite:///./access_governance.db')
config.set_main_option('sqlalchemy.url',url.replace('%','%%'))

def offline():
    context.configure(url=url,target_metadata=Base.metadata,literal_binds=True,
                      dialect_opts={'paramstyle':'named'},render_as_batch=True)
    with context.begin_transaction(): context.run_migrations()

def online():
    engine=engine_from_config(config.get_section(config.config_ini_section),
                        prefix='sqlalchemy.',poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=Base.metadata,
                          render_as_batch=True,compare_type=True)
        with context.begin_transaction():context.run_migrations()
    engine.dispose()

if context.is_offline_mode(): offline()
else: online()
