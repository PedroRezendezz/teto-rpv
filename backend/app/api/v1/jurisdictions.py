"""
Endpoints auxiliares de jurisdições (autocomplete, listagem).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.schemas import JurisdictionOut
from app.database import get_db
from app.models.jurisdiction import Jurisdiction
from app.services.normalizer import normalize

router = APIRouter()


@router.get("/jurisdictions", response_model=list[JurisdictionOut])
def list_jurisdictions(
    q: str = Query(default="", description="Filtro por nome"),
    level: str = Query(default="", description="federal | state | municipal"),
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Jurisdiction)

    if level:
        query = query.filter(Jurisdiction.level == level)

    if q:
        normalized = normalize(q)
        from sqlalchemy import text
        query = query.filter(
            text("similarity(lower(name), :q) > 0.2").bindparams(q=normalized)
        ).order_by(text("similarity(lower(name), :q) DESC").bindparams(q=normalized))
    else:
        query = query.order_by(Jurisdiction.level, Jurisdiction.name)

    return query.limit(limit).all()


@router.get("/jurisdictions/{jurisdiction_id}", response_model=JurisdictionOut)
def get_jurisdiction(jurisdiction_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    j = db.query(Jurisdiction).filter(Jurisdiction.id == jurisdiction_id).first()
    if not j:
        raise HTTPException(status_code=404, detail="Jurisdição não encontrada.")
    return j
