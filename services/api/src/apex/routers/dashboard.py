"""`GET /dashboard` (J3) — les quatre indicateurs du dirigeant, **lus en une seule
requête SQL** et servis tels quels.

La règle du plan : aucun calcul dans l'interface. Un chiffre recalculé côté UI finit
toujours par diverger de celui du backend le jour où une règle change d'un seul côté — et
c'est le genre d'écart qu'on découvre devant un client.

Une seule requête, aussi, parce que quatre allers-retours pour quatre nombres réveilleraient
quatre fois le compute d'une base serverless mise en veille (§3-C) : la latence du tableau
de bord vaut ici bien plus que l'élégance de quatre requêtes séparées.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlalchemy import text
from sqlalchemy.orm import Session

from apex.db import get_db
from apex.routers._common import bearer_scheme
from apex.routers.stats import auto_attach_rate
from apex.schemas.stats import DashboardOut, MediaIngestedVolume
from apex.security import CurrentUser
from apex.services import access

router = APIRouter(tags=["dashboard"], dependencies=[Security(bearer_scheme)])

#: Un seul aller-retour. Chaque sous-requête est un agrégat sur des colonnes indexées ;
#: `media` est la seule table volumineuse, et son décompte porte sur `is_simulated` et
#: `attachment_status`, tous deux dans la projection de recherche déjà indexée.
_DASHBOARD_SQL = text(
    """
    WITH bornes AS (
        SELECT CAST(:from_date AS timestamptz) AS debut,
               CAST(:to_date AS timestamptz) AS fin
    ),
    facturation AS (
        SELECT coalesce(sum(total_cents), 0) AS revenue_cents
          FROM invoice, bornes
         WHERE status = 'issued'
           AND (bornes.debut IS NULL OR issued_at >= bornes.debut)
           AND (bornes.fin IS NULL OR issued_at < bornes.fin)
    ),
    prises_de_vue AS (
        SELECT
            count(*) FILTER (WHERE status = 'done') AS shootings_done,
            count(*) FILTER (WHERE status = 'planned' AND starts_at >= now())
                AS shootings_upcoming
          FROM shooting, bornes
         WHERE (bornes.debut IS NULL OR starts_at >= bornes.debut)
           AND (bornes.fin IS NULL OR starts_at < bornes.fin)
    ),
    volumes AS (
        SELECT
            count(*) FILTER (WHERE NOT is_simulated) AS reels,
            count(*) FILTER (WHERE is_simulated) AS simules,
            count(*) AS total
          FROM media, bornes
         WHERE ingest_status <> 'quarantined'
           AND (bornes.debut IS NULL OR created_at >= bornes.debut)
           AND (bornes.fin IS NULL OR created_at < bornes.fin)
    )
    SELECT facturation.revenue_cents,
           prises_de_vue.shootings_done,
           prises_de_vue.shootings_upcoming,
           volumes.reels,
           volumes.simules,
           volumes.total
      FROM facturation, prises_de_vue, volumes
    """
)


def _parse_date(value: str | None, field: str) -> datetime | None:
    """`YYYY-MM-DD` ou ISO complet. Une borne illisible est refusée plutôt qu'ignorée :
    un tableau de bord qui affiche silencieusement « tout l'historique » quand on lui
    demande « ce mois-ci » est pire qu'une erreur."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(value), datetime.min.time())
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_date",
                    "message": f"Le paramètre « {field} » n'est pas une date valide.",
                    "detail": {"value": value},
                },
            ) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@router.get("/dashboard", response_model=DashboardOut, summary="Tableau de bord dirigeant")
def dashboard(
    user: CurrentUser,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    db: Session = Depends(get_db),
) -> DashboardOut:
    access.require_owner(user, message="Le tableau de bord est réservé au dirigeant.")
    row = db.execute(
        _DASHBOARD_SQL,
        {"from_date": _parse_date(from_, "from"), "to_date": _parse_date(to, "to")},
    ).one()

    total = int(row.total)
    return DashboardOut(
        revenue_cents=int(row.revenue_cents),
        shootings_done=int(row.shootings_done),
        shootings_upcoming=int(row.shootings_upcoming),
        media_ingested=MediaIngestedVolume(
            real=int(row.reels), simulated=int(row.simules), total=total
        ),
        # **Réutilisé, jamais recalculé.** Le taux de rattachement automatique a une
        # définition précise et peu intuitive (un média rattaché par l'OCR mais arbitré par
        # un humain ne compte pas comme automatique, les doublons sont exclus, …) : la
        # réécrire ici en SQL produirait deux chiffres différents sous le même nom, et
        # personne ne saurait lequel croire. Le coût est une requête de plus.
        auto_attach_rate=auto_attach_rate(user=user, from_=from_, to=to, db=db).rate,
    )
