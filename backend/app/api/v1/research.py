"""
Endpoint de polling para jobs de pesquisa assíncrona.

GET /api/v1/research-status/{job_id}
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.schemas import CeilingOut, JurisdictionOut, ResearchStatusResponse
from app.database import get_db
from app.models.jurisdiction import Jurisdiction
from app.models.research_log import ResearchLog
from app.services.ceiling_calc import calculate_brl_equivalent

router = APIRouter()


@router.get("/research-status/{job_id}", response_model=ResearchStatusResponse)
def research_status(job_id: int, db: Session = Depends(get_db)):
    log = db.query(ResearchLog).filter(ResearchLog.id == job_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    if log.status in ("pending", "running"):
        return ResearchStatusResponse(job_id=str(job_id), status=log.status)

    if log.status == "failed":
        return ResearchStatusResponse(
            job_id=str(job_id), status="failed", error=log.error_message
        )

    # Concluído — retorna dados
    if not log.jurisdiction_id:
        return ResearchStatusResponse(
            job_id=str(job_id),
            status="completed",
            error="Jurisdição não encontrada na pesquisa.",
        )

    jurisdiction = db.query(Jurisdiction).filter(
        Jurisdiction.id == log.jurisdiction_id
    ).first()

    if not jurisdiction:
        return ResearchStatusResponse(job_id=str(job_id), status="completed")

    ceilings_out = []
    for c in jurisdiction.ceilings:
        brl = calculate_brl_equivalent(
            db, c.ceiling_type, c.ceiling_value, c.valid_until or date.today()
        )
        ceilings_out.append(
            CeilingOut(
                id=c.id,
                valid_from=c.valid_from,
                valid_until=c.valid_until,
                ceiling_description=c.ceiling_description,
                ceiling_type=c.ceiling_type,
                ceiling_value=float(c.ceiling_value) if c.ceiling_value else None,
                brl_equivalent=brl,
                legislation_name=c.legislation_name,
                legislation_url=c.legislation_url,
                legislation_description=c.legislation_description,
                uses_federal_fallback=c.uses_federal_fallback,
                confidence=c.confidence,
                flagged_for_review=c.flagged_for_review,
            )
        )

    return ResearchStatusResponse(
        job_id=str(job_id),
        status="completed",
        jurisdiction=JurisdictionOut.model_validate(jurisdiction),
        ceilings=ceilings_out,
    )
