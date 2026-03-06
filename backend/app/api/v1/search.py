"""
Endpoint principal de busca — orquestra a lógica cache-hit / cache-miss / stale-refresh.

Lógica de atualização:
- Dados com mais de STALE_DAYS sem re-pesquisa → retorna cache imediatamente
  + dispara re-pesquisa silenciosa em background (usuário não espera)
- Dados históricos (valid_until != null) nunca re-pesquisados (lei passada não muda)
- Apenas teto vigente (valid_until = null) é verificado por staleness
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.schemas import CeilingOut, JurisdictionOut, SearchResponse
from app.database import get_db
from app.models.jurisdiction import Jurisdiction
from app.models.research_log import ResearchLog
from app.services.ceiling_calc import calculate_brl_equivalent
from app.services.normalizer import resolve_jurisdiction

router = APIRouter()

STALE_DAYS = 90


def _build_ceiling_out(ceiling, db: Session) -> CeilingOut:
    brl = calculate_brl_equivalent(
        db,
        ceiling.ceiling_type,
        ceiling.ceiling_value,
        ceiling.valid_until or date.today(),
    )
    return CeilingOut(
        id=ceiling.id,
        valid_from=ceiling.valid_from,
        valid_until=ceiling.valid_until,
        ceiling_description=ceiling.ceiling_description,
        ceiling_type=ceiling.ceiling_type,
        ceiling_value=float(ceiling.ceiling_value) if ceiling.ceiling_value else None,
        brl_equivalent=brl,
        legislation_name=ceiling.legislation_name,
        legislation_url=ceiling.legislation_url,
        legislation_description=ceiling.legislation_description,
        uses_federal_fallback=ceiling.uses_federal_fallback,
        confidence=ceiling.confidence,
        flagged_for_review=ceiling.flagged_for_review,
    )


def _is_stale(jurisdiction: Jurisdiction) -> bool:
    if not jurisdiction.last_researched:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)
    return jurisdiction.last_researched < cutoff


def _trigger_refresh(db: Session, background_tasks: BackgroundTasks, jurisdiction: Jurisdiction) -> None:
    pending = (
        db.query(ResearchLog)
        .filter(
            ResearchLog.jurisdiction_id == jurisdiction.id,
            ResearchLog.status.in_(["pending", "running"]),
        )
        .first()
    )
    if pending:
        return

    log = ResearchLog(
        jurisdiction_id=jurisdiction.id,
        search_query=jurisdiction.name,
        status="pending",
        triggered_by="scheduled",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    from app.services.ai_agent import run_research
    background_tasks.add_task(run_research, log.id, jurisdiction.name, jurisdiction.id)


@router.get("/search", response_model=SearchResponse)
def search(q: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=422, detail="Query muito curta.")

    candidates = resolve_jurisdiction(db, q)

    if not candidates:
        log = ResearchLog(search_query=q, status="pending", triggered_by="user_query")
        db.add(log)
        db.commit()
        db.refresh(log)
        from app.services.ai_agent import run_research
        background_tasks.add_task(run_research, log.id, q, None)
        return SearchResponse(
            status="researching",
            job_id=str(log.id),
            message=f"Não encontramos '{q}' no banco. Pesquisando legislação...",
        )

    if len(candidates) > 1:
        return SearchResponse(
            status="ambiguous",
            candidates=[JurisdictionOut.model_validate(c) for c in candidates],
            message=f"Encontramos {len(candidates)} jurisdições para '{q}'. Selecione uma.",
        )

    jurisdiction: Jurisdiction = candidates[0]

    if not jurisdiction.ceilings:
        log = ResearchLog(
            jurisdiction_id=jurisdiction.id,
            search_query=q,
            status="pending",
            triggered_by="user_query",
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        from app.services.ai_agent import run_research
        background_tasks.add_task(run_research, log.id, jurisdiction.name, jurisdiction.id)
        return SearchResponse(
            status="researching",
            job_id=str(log.id),
            message=f"Encontramos {jurisdiction.name} mas ainda não temos dados de teto. Pesquisando...",
        )

    stale = _is_stale(jurisdiction)
    if stale:
        _trigger_refresh(db, background_tasks, jurisdiction)

    ceilings_out = [_build_ceiling_out(c, db) for c in jurisdiction.ceilings]
    data_age_days = None
    if jurisdiction.last_researched:
        data_age_days = (datetime.now(timezone.utc) - jurisdiction.last_researched).days

    return SearchResponse(
        status="found",
        jurisdiction=JurisdictionOut.model_validate(jurisdiction),
        ceilings=ceilings_out,
        stale_refresh_triggered=stale,
        data_age_days=data_age_days,
    )
