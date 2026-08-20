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
