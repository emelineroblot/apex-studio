"""Configuration applicative — chargée depuis l'environnement (`.env` en local).

Toutes les variables listées en §3-A.5 du plan. Aucun secret par défaut utilisable en
production : les valeurs ci-dessous sont des repères de développement uniquement.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    app_name: str = "Apex"
    studio_name: str = "Studio Chicane"

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


@lru_cache
def get_settings() -> Settings:
    """Instance mise en cache — évite de reparser l'environnement à chaque appel."""
    return Settings()


settings = get_settings()
