"""
Endpoints administrativos — histórico de pesquisas e dados coletados.
"""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.schemas import HistoryItem
from app.database import get_db
from app.models.ceiling import RpvCeiling
from app.models.jurisdiction import Jurisdiction
from app.services.ceiling_calc import calculate_brl_equivalent

router = APIRouter()


@router.get("/admin/history", response_model=list[HistoryItem])
def get_history(db: Session = Depends(get_db)):
    """
    Retorna todas as jurisdições que já foram pesquisadas,
    com o teto vigente de cada uma e o timestamp da última consulta.
    Ordenado por mais recente primeiro.
    """
    jurisdictions = (
        db.query(Jurisdiction)
        .filter(Jurisdiction.last_researched.isnot(None))
        .order_by(Jurisdiction.last_researched.desc())
        .all()
    )

    items = []
    for j in jurisdictions:
        # Pega o teto vigente (valid_until = null)
        current = (
            db.query(RpvCeiling)
            .filter(
                RpvCeiling.jurisdiction_id == j.id,
                RpvCeiling.valid_until.is_(None),
            )
            .first()
        )

        if current:
            brl = calculate_brl_equivalent(
                db,
                current.ceiling_type,
                current.ceiling_value,
                date.today(),
            )
            items.append(HistoryItem(
                jurisdiction_id=j.id,
                jurisdiction_name=j.name,
                level=j.level,
                uf=j.uf,
                teto_vigente=current.ceiling_description,
                valor_brl=brl,
                legislation_name=current.legislation_name,
                legislation_url=current.legislation_url,
                confidence=current.confidence,
                uses_federal_fallback=current.uses_federal_fallback,
                last_researched=j.last_researched,
            ))
        else:
            items.append(HistoryItem(
                jurisdiction_id=j.id,
                jurisdiction_name=j.name,
                level=j.level,
                uf=j.uf,
                last_researched=j.last_researched,
            ))

    return items
