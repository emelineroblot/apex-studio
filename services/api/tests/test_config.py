"""Verrouille le correctif fail-closed du bloquant revue J1 n°5 (config des secrets).

Signalé par l'orchestrateur : le premier correctif posait `app_env: str = "local"`,
ce qui rendait `_reject_default_secrets_outside_local` fail-**open** — une variable
`APP_ENV` oubliée au déploiement (aussi vraisemblable qu'un `JWT_SECRET` oublié, le
scénario même de la revue) retombait sur `"local"` et désactivait silencieusement la
validation, laissant le secret par défaut actif. `app_env` vaut désormais `"production"`
par défaut : l'absence totale de configuration doit faire échouer le démarrage, pas
réussir silencieusement.
"""

from __future__ import annotations

import pytest

from apex.config import Settings


def test_settings_rejects_default_secrets_when_nothing_is_configured(monkeypatch) -> None:
    """Reproduit le scénario exact de la revue : ni `APP_ENV` ni `JWT_SECRET` ne sont
    posés nulle part (ni variable d'environnement, ni `.env`). Avant le correctif de
    suivi, ceci démarrait avec succès (`app_env` retombait sur `"local"`,
    `jwt_secret="dev-secret-change-me"` restait actif) — ça doit désormais lever.
    """
    for name in (
        "APP_ENV",
        "JWT_SECRET",
        "WORKER_SECRET",
        "CRON_SECRET",
        "DEMO_OWNER_PASSWORD",
        "DEMO_PHOTOGRAPHER_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    # `_env_file=None` : neutralise le `.env` local (qui pose `APP_ENV=local` pour le
    # développement) — le scénario testé est « rien n'est configuré nulle part »,
    # pas « le `.env` de la développeuse a été chargé par erreur ».
    with pytest.raises(RuntimeError, match="D.marrage refus."):
        Settings(_env_file=None)


def test_settings_starts_when_app_env_is_local(monkeypatch) -> None:
    """Non-régression : le développement local (`APP_ENV=local` explicite) démarre
    toujours avec les valeurs par défaut, sans lever.
    """
    monkeypatch.setenv("APP_ENV", "local")
    for name in (
        "JWT_SECRET",
        "WORKER_SECRET",
        "CRON_SECRET",
        "DEMO_OWNER_PASSWORD",
        "DEMO_PHOTOGRAPHER_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)
    assert settings.app_env == "local"
    assert settings.jwt_secret == "dev-secret-change-me"


def test_settings_starts_in_production_when_secrets_are_overridden(monkeypatch) -> None:
    """Non-régression : `APP_ENV=production` avec de vrais secrets démarre sans lever."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "un-vrai-secret-genere")
    monkeypatch.setenv("WORKER_SECRET", "un-vrai-secret-worker")
    monkeypatch.setenv("CRON_SECRET", "un-vrai-secret-cron")
    monkeypatch.setenv("DEMO_OWNER_PASSWORD", "un-vrai-mdp-owner")
    monkeypatch.setenv("DEMO_PHOTOGRAPHER_PASSWORD", "un-vrai-mdp-photographe")

    settings = Settings(_env_file=None)
    assert settings.app_env == "production"


class TestConnexionSupabase:
    """Deux chaînes de connexion, jamais interchangeables (§ « Bascule vers Supabase »).

    Un pooler en mode transaction multiplexe les connexions : il ne peut porter ni une
    migration de schéma, ni des instructions préparées. Ces deux comportements sont donc
    dérivés de la configuration, pas laissés à la vigilance de celle qui déploie.
    """

    def _settings(self, monkeypatch, **overrides: str):
        for name in ("APP_ENV", "DATABASE_URL", "DATABASE_URL_DIRECT"):
            monkeypatch.delenv(name, raising=False)
        base = {
            "jwt_secret": "x" * 32,
            "worker_secret": "y" * 32,
            "cron_secret": "z" * 32,
            "demo_owner_password": "owner-password",
            "demo_photographer_password": "photographer-password",
        }
        return Settings(_env_file=None, **{**base, **overrides})

    def test_alembic_prend_la_session_pooler_quand_elle_est_fournie(self, monkeypatch) -> None:
        settings = self._settings(
            monkeypatch,
            database_url="postgresql+psycopg://u:p@pooler:6543/postgres",
            database_url_direct="postgresql+psycopg://u:p@pooler:5432/postgres",
        )
        assert settings.migration_database_url.endswith(":5432/postgres")
        # L'API, elle, continue de passer par le pooler en mode transaction.
        assert settings.database_url.endswith(":6543/postgres")

    def test_sans_session_pooler_les_migrations_reprennent_lurl_principale(
        self, monkeypatch
    ) -> None:
        """En local, il n'y a pas de pooler : les deux se confondent, et rien n'oblige la
        développeuse à renseigner une variable qui n'a pas de sens chez elle."""
        settings = self._settings(
            monkeypatch,
            app_env="local",
            database_url="postgresql+psycopg://u:p@localhost:5432/apex",
        )
        assert settings.migration_database_url == settings.database_url

    def test_les_contournements_du_pooler_sont_actifs_partout_sauf_en_local(
        self, monkeypatch
    ) -> None:
        """`is_remote` est volontairement plus large que « production » : un déploiement de
        prévisualisation passe par le même pooler et rencontre les mêmes limites."""
        assert self._settings(monkeypatch, app_env="local").is_remote is False
        assert self._settings(monkeypatch, app_env="production").is_remote is True
        assert self._settings(monkeypatch, app_env="preview").is_remote is True
