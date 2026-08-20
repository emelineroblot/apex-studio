"""Configuration applicative — chargée depuis l'environnement (`.env` en local).

Toutes les variables listées en §3-A.5 du plan.

**Correction revue J1 (🔴 n°5)** : les valeurs par défaut ci-dessous ne sont *jamais*
utilisables telles quelles en production — le dépôt est public, donc `jwt_secret:
"dev-secret-change-me"` par exemple est un secret forgeable par quiconque lit le code.
`_reject_default_secrets_outside_local` refuse le **démarrage** de l'application si l'une
de ces valeurs par défaut est encore active alors que `APP_ENV != "local"` : mieux vaut un
crash au déploiement qu'un secret public silencieusement actif.

**Fail-closed (correctif de suivi)** : `app_env` vaut `"production"` par défaut — pas
`"local"`. Une variable `APP_ENV` oubliée au déploiement (aussi vraisemblable qu'un
`JWT_SECRET` oublié, exactement le scénario visé par la revue) est donc traitée comme la
production, pas comme un environnement de confiance. Seul un `APP_ENV=local` posé
explicitement (`.env`, `.env.example`, `tests/conftest.py`) désactive la validation.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Correspondance nom de variable d'environnement -> valeur de développement par défaut.
#: Toute valeur ici est un secret **connu de quiconque lit ce fichier** (dépôt public) —
#: jamais acceptable hors `APP_ENV=local` (§3-I, revue J1 bloquant n°5).
_UNSAFE_DEFAULTS = {
    "JWT_SECRET": "dev-secret-change-me",
    "WORKER_SECRET": "dev-worker-secret",
    "CRON_SECRET": "dev-cron-secret",
    "DEMO_OWNER_PASSWORD": "changeme-owner",
    "DEMO_PHOTOGRAPHER_PASSWORD": "changeme-photographer",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    app_name: str = "Apex"
    studio_name: str = "Studio Chicane"
    # `production` (défaut **fail-closed**, revue J1 : le premier correctif posait
    # `app_env: str = "local"`, ce qui rendait le garde-fou ci-dessous fail-open — une
    # variable APP_ENV oubliée (aussi probable qu'un JWT_SECRET oublié, le scénario même
    # de la revue) retombait sur "local" et désactivait silencieusement la validation).
    # Le développement local doit désormais déclarer explicitement `APP_ENV=local`
    # (`.env`/`.env.example`, `tests/conftest.py`) ; tout le reste — y compris l'absence
    # totale de la variable — est traité comme strict par défaut.
    app_env: str = "production"

    # --- Base de données ---
    database_url: str = "postgresql+psycopg://apex:apex@localhost:55432/apex"

    # --- Auth ---
    jwt_secret: str = "dev-secret-change-me"
    jwt_ttl_minutes: int = 480
    client_session_ttl_minutes: int = 30

    # --- Stockage objet (Cloudflare R2, jurisdiction eu) ---
    s3_endpoint_url: str = "https://example.r2.cloudflarestorage.com"
    s3_region: str = "auto"
    s3_bucket: str = "apex-dev"
    s3_access_key_id: str = "changeme"
    s3_secret_access_key: str = "changeme"
    # `local` par défaut (§5 du plan : dev/tests sans compte Cloudflare) ; `s3` en prod.
    storage_backend: str = "local"
    storage_local_dir: str = "./storage"

    # --- Frontend / liens publics ---
    web_origin: str = "http://localhost:3000"
    public_web_base_url: str = "http://localhost:3000"

    # --- Worker / cron (serverless) ---
    worker_secret: str = "dev-worker-secret"
    cron_secret: str = "dev-cron-secret"

    # --- Comptes de démo (seed) ---
    demo_owner_password: str = "changeme-owner"
    demo_photographer_password: str = "changeme-photographer"

    # --- OCR (J2) ---
    ocr_model_dir: str = "./models"

    # --- Limites ---
    max_upload_bytes: int = 26_214_400
    default_shooting_quota_bytes: int = 2_147_483_648

    @model_validator(mode="after")
    def _reject_default_secrets_outside_local(self) -> "Settings":
        if self.app_env == "local":
            return self
        field_values = {
            "JWT_SECRET": self.jwt_secret,
            "WORKER_SECRET": self.worker_secret,
            "CRON_SECRET": self.cron_secret,
            "DEMO_OWNER_PASSWORD": self.demo_owner_password,
            "DEMO_PHOTOGRAPHER_PASSWORD": self.demo_photographer_password,
        }
        leaking = [
            name for name, default in _UNSAFE_DEFAULTS.items() if field_values[name] == default
        ]
        if leaking:
            raise RuntimeError(
                "Démarrage refusé : APP_ENV="
                f"« {self.app_env} » (hors « local ») mais les variables d'environnement "
                f"suivantes n'ont pas été redéfinies et gardent leur valeur par défaut du "
                f"dépôt (public, donc forgeable) : {', '.join(leaking)}. Définissez-les "
                "explicitement avant de redéployer."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Instance mise en cache — évite de reparser l'environnement à chaque appel."""
    return Settings()


settings = get_settings()
