"""Environnement Alembic — DATABASE_URL réel injecté depuis `apex.config.settings`
(§ alembic.ini). L'environnement est jetable (AGENTS.md) : pas de mode « offline »
soigné, on cible toujours une base réelle atteignable.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importer `apex.models` (et non un sous-module isolé) charge toute la métadonnée du
# schéma des 3 jalons dans `Base.metadata` — nécessaire pour l'autogenerate.
from apex.config import settings
from apex.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Le DATABASE_URL applicatif fait foi ; la valeur de alembic.ini n'est qu'un repli.
# `migration_database_url` : la chaîne « Session pooler » quand elle est fournie
# (`DATABASE_URL_DIRECT`), sinon `DATABASE_URL`. Un pooler en mode transaction multiplexe
# les connexions et ne peut pas porter une migration de schéma.
# `%` doublé : `set_main_option` écrit dans un `ConfigParser`, qui traite `%` comme une
# interpolation (`%(clé)s`) et lève `ValueError: invalid interpolation syntax` sur toute URL
# qui en contient. Or un mot de passe est URL-encodé dès qu'il porte un caractère spécial —
# `$` devient `%24`, `!` devient `%21` — ce qui est le cas courant d'un mot de passe généré
# par un hébergeur. Rencontré au premier `alembic upgrade head` contre Supabase.
config.set_main_option("sqlalchemy.url", settings.migration_database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Génère du SQL sans connexion — non utilisé en pratique (environnement jetable)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Mode standard : connexion réelle à la base ciblée par DATABASE_URL."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
