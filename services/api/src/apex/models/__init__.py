"""Modèles SQLAlchemy des 28 tables du schéma complet (3 jalons).

Importer ce module (plutôt que des sous-modules isolés) garantit que `Base.metadata`
connaît toutes les tables — nécessaire pour qu'Alembic `env.py` s'y réfère correctement.
"""

from apex.models.base import Base
from apex.models.billing import (
    ClientSelection,
    Delivery,
    Invoice,
    InvoiceLine,
    Quote,
    SelectionItem,
    ShareLink,
)
from apex.models.catalog import Camera, Circuit, Client, Driver, Team
from apex.models.collection import Collection, CollectionItem
from apex.models.job import Job, JobExecutionLog
from apex.models.media import (
    Media,
    MediaEngagement,
    MediaSeries,
    PipelineEvent,
    UploadBatch,
)
from apex.models.search import MediaOcrCandidate, MediaSearch
from apex.models.setting import AppSetting
from apex.models.shooting import Engagement, Shooting, ShootingStaff
from apex.models.user import AppUser

__all__ = [
    "Base",
    "AppUser",
    "Client",
    "Circuit",
    "Team",
    "Driver",
    "Camera",
    "Shooting",
    "ShootingStaff",
    "Engagement",
    "UploadBatch",
    "Media",
    "MediaSeries",
    "MediaEngagement",
    "PipelineEvent",
    "Job",
    "JobExecutionLog",
    "AppSetting",
    "MediaOcrCandidate",
    "MediaSearch",
    "Collection",
    "CollectionItem",
    "ShareLink",
    "ClientSelection",
    "SelectionItem",
    "Delivery",
    "Quote",
    "Invoice",
    "InvoiceLine",
]
