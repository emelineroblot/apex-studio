"""Une URL de base contenant `%` doit rester utilisable par Alembic.

`alembic/env.py` écrit l'URL dans un `ConfigParser` (`config.set_main_option`), et
`ConfigParser` traite `%` comme le début d'une interpolation (`%(clé)s`). Or un mot de
passe est URL-encodé dès qu'il porte un caractère spécial — `$` devient `%24`, `!` devient
`%21` — ce qui est le cas courant d'un mot de passe généré par un hébergeur.

Rencontré au premier `alembic upgrade head` contre Supabase : `ValueError: invalid
interpolation syntax`. Aucun test ne pouvait le voir, toutes les URL de développement du
projet étant en ASCII simple.
"""

from __future__ import annotations

import pytest
from alembic.config import Config

#: Forme réelle d'une chaîne Supabase dont le mot de passe contient `$` et `!`.
URL_AVEC_POURCENTS = (
    "postgresql+psycopg://postgres.abcdefghijklmnop:%24%21MotDePasse%21@"
    "aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
)


def test_une_url_avec_pourcents_casse_configparser_si_elle_nest_pas_echappee() -> None:
    """Le comportement qu'on contourne — s'il disparaissait un jour, le doublage
    deviendrait inutile et ce test le signalerait."""
    with pytest.raises(ValueError, match="interpolation"):
        Config().set_main_option("sqlalchemy.url", URL_AVEC_POURCENTS)


def test_le_doublage_rend_lurl_acceptable_et_la_restitue_intacte() -> None:
    config = Config()
    config.set_main_option("sqlalchemy.url", URL_AVEC_POURCENTS.replace("%", "%%"))
    # Relue, l'URL doit être exactement celle de départ : le doublage est un détail
    # d'écriture, jamais une transformation de la valeur.
    assert config.get_main_option("sqlalchemy.url") == URL_AVEC_POURCENTS


def test_une_url_sans_pourcent_traverse_le_doublage_sans_changer() -> None:
    simple = "postgresql+psycopg://apex:apex@localhost:55432/apex"
    config = Config()
    config.set_main_option("sqlalchemy.url", simple.replace("%", "%%"))
    assert config.get_main_option("sqlalchemy.url") == simple
