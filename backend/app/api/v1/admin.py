"""
Endpoints administrativos — histórico de pesquisas, estatísticas de uso e seeds.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.schemas import HistoryItem
from app.database import get_db
from app.models.ceiling import RpvCeiling
from app.models.jurisdiction import Jurisdiction
from app.models.research_log import ResearchLog
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


@router.get("/admin/stats")
def get_stats(db: Session = Depends(get_db)):
    """
    Retorna estatísticas de uso: total de pesquisas, custo, tokens e atividade diária.
    """
    total = db.query(func.count(ResearchLog.id)).scalar() or 0
    completed = (
        db.query(func.count(ResearchLog.id))
        .filter(ResearchLog.status == "completed")
        .scalar() or 0
    )
    failed = (
        db.query(func.count(ResearchLog.id))
        .filter(ResearchLog.status == "failed")
        .scalar() or 0
    )
    pending = (
        db.query(func.count(ResearchLog.id))
        .filter(ResearchLog.status.in_(["pending", "running"]))
        .scalar() or 0
    )
    total_tokens = int(db.query(func.sum(ResearchLog.tokens_used)).scalar() or 0)
    total_cost = float(db.query(func.sum(ResearchLog.estimated_cost_usd)).scalar() or 0)
    jurisdictions_researched = (
        db.query(func.count(Jurisdiction.id))
        .filter(Jurisdiction.last_researched.isnot(None))
        .scalar() or 0
    )

    # Atividade diária (últimos 30 dias)
    daily = (
        db.query(
            func.date_trunc("day", ResearchLog.started_at).label("day"),
            func.count(ResearchLog.id).label("searches"),
            func.coalesce(func.sum(ResearchLog.estimated_cost_usd), 0).label("cost"),
        )
        .group_by(func.date_trunc("day", ResearchLog.started_at))
        .order_by(func.date_trunc("day", ResearchLog.started_at).desc())
        .limit(30)
        .all()
    )

    # Log de pesquisas recentes
    recent = (
        db.query(ResearchLog)
        .order_by(ResearchLog.started_at.desc())
        .limit(20)
        .all()
    )

    # Tetos atualizados nos últimos 30 dias
    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
    recent_updates = (
        db.query(RpvCeiling, Jurisdiction)
        .join(Jurisdiction, RpvCeiling.jurisdiction_id == Jurisdiction.id)
        .filter(
            RpvCeiling.updated_at >= cutoff_30d,
            RpvCeiling.valid_until.is_(None),
        )
        .order_by(RpvCeiling.updated_at.desc())
        .limit(20)
        .all()
    )

    return {
        "total_searches": total,
        "completed": completed,
        "failed": failed,
        "pending": pending,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 5),
        "jurisdictions_researched": jurisdictions_researched,
        "daily_activity": [
            {
                "day": str(r.day.date()),
                "searches": r.searches,
                "cost_usd": round(float(r.cost), 5),
            }
            for r in daily
        ],
        "recent_searches": [
            {
                "query": r.search_query,
                "status": r.status,
                "tokens": r.tokens_used,
                "cost_usd": round(float(r.estimated_cost_usd), 5) if r.estimated_cost_usd else None,
                "model": r.ai_model_used,
                "started_at": r.started_at.isoformat() if r.started_at else None,
            }
            for r in recent
        ],
        "recent_ceiling_updates": [
            {
                "jurisdiction": j.name,
                "uf": j.uf,
                "level": j.level,
                "teto": c.ceiling_description,
                "legislation": c.legislation_name,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c, j in recent_updates
        ],
    }


@router.post("/admin/trigger-state-research")
async def trigger_state_research(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Dispara pesquisa de IA para todos os estados que ainda não têm dados de teto.
    Estados com dados existentes ou jobs em andamento são ignorados.
    """
    from app.services.ai_agent import run_research

    states = db.query(Jurisdiction).filter(Jurisdiction.level == "state").all()

    triggered = []
    skipped = []
    for state in states:
        has_ceiling = (
            db.query(RpvCeiling)
            .filter(RpvCeiling.jurisdiction_id == state.id)
            .first()
        )
        if has_ceiling:
            skipped.append(state.name)
            continue

        pending_job = (
            db.query(ResearchLog)
            .filter(
                ResearchLog.jurisdiction_id == state.id,
                ResearchLog.status.in_(["pending", "running"]),
            )
            .first()
        )
        if pending_job:
            skipped.append(state.name)
            continue

        log = ResearchLog(
            jurisdiction_id=state.id,
            search_query=state.name,
            status="pending",
            triggered_by="manual_seed",
        )
        db.add(log)
        db.flush()
        background_tasks.add_task(run_research, log.id, state.name, state.id)
        triggered.append(state.name)

    db.commit()
    return {
        "triggered": len(triggered),
        "skipped": len(skipped),
        "states_triggered": triggered,
    }
