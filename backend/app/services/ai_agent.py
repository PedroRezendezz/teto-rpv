"""
AI Research Agent — usa Tavily (busca) + Claude Haiku (extração).

Estratégia otimizada para mínimo custo:
1. Tavily faz todas as buscas na web (grátis, até 1.000/mês)
2. Claude recebe o conteúdo já coletado e apenas extrai/estrutura o JSON
   → 1 chamada ao invés de 2-3 rounds de tool_use com Opus
3. State cascade: municípios herdam do estado quando não há lei própria

Custo estimado por pesquisa: ~$0.003 (haiku) vs ~$0.16 (opus anterior)
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.ceiling import RpvCeiling
from app.models.jurisdiction import Jurisdiction
from app.models.research_log import ResearchLog
from app.services.normalizer import normalize

logger = logging.getLogger(__name__)

# Haiku: $0.80/M input, $4/M output — 18x mais barato que Opus
RESEARCH_MODEL = "claude-haiku-4-5-20251001"
COST_PER_INPUT_TOKEN = 0.80 / 1_000_000
COST_PER_OUTPUT_TOKEN = 4.00 / 1_000_000

EXTRACTION_PROMPT = """Você é um extrator de dados jurídicos. Com base nos resultados de busca abaixo, extraia o histórico de tetos de RPV.

Jurisdição: {jurisdiction_name} (nível: {level}){state_context}

RESULTADOS DA BUSCA:
{search_results}

Retorne APENAS um JSON válido (sem texto antes ou depois):
{{
  "uses_federal_fallback": false,
  "ceilings": [
    {{
      "valid_from": "YYYY-MM-DD",
      "valid_until": "YYYY-MM-DD ou null",
      "ceiling_type": "salary_multiple ou fixed_brl",
      "ceiling_value": 60.0,
      "ceiling_description": "60 salários mínimos",
      "legislation_name": "Lei nº X/AAAA",
      "legislation_url": "https://... ou null",
      "legislation_description": "Descrição breve"
    }}
  ],
  "confidence": "high ou medium ou low",
  "research_notes": "notas sobre fontes e confiança"
}}

Se não houver lei local, retorne uses_federal_fallback=true e ceilings=[]."""


def run_research(log_id: int, query: str, jurisdiction_id: Optional[int]) -> None:
    db = SessionLocal()
    try:
        _do_research(db, log_id, query, jurisdiction_id)
    except Exception as e:
        logger.error(f"Erro no research job {log_id}: {e}")
        log = db.query(ResearchLog).filter(ResearchLog.id == log_id).first()
        if log:
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def _do_research(db: Session, log_id: int, query: str, jurisdiction_id: Optional[int]) -> None:
    log = db.query(ResearchLog).filter(ResearchLog.id == log_id).first()
    if not log:
        return

    log.status = "running"
    log.ai_model_used = RESEARCH_MODEL
    db.commit()

    # Resolve jurisdição e contexto
    level, state_context, jurisdiction = _resolve_context(db, query, jurisdiction_id)

    # Otimização: state cascade para municípios
    # Se o estado já tem dados e usa fallback federal, o município provavelmente também usa
    if level == "municipal" and jurisdiction and jurisdiction.state_id:
        state = db.query(Jurisdiction).filter(Jurisdiction.id == jurisdiction.state_id).first()
        if state and state.ceilings:
            state_uses_fallback = all(c.uses_federal_fallback for c in state.ceilings)
            if state_uses_fallback:
                _save_municipal_cascade(db, jurisdiction, state, log)
                log.status = "completed"
                log.completed_at = datetime.now(timezone.utc)
                log.research_notes = "Herdado do estado via cascade (estado usa fallback federal)"
                db.commit()
                logger.info(f"Job {log_id}: cascade do estado, sem chamada de IA.")
                return

    # Etapa 1: Tavily busca o conteúdo (grátis)
    search_results = _collect_search_results(query, level, state_context)

    # Etapa 2: Claude extrai o JSON do conteúdo coletado (1 única chamada)
    parsed, input_tokens, output_tokens = _extract_with_claude(
        query, level, state_context, search_results
    )

    cost = (input_tokens * COST_PER_INPUT_TOKEN) + (output_tokens * COST_PER_OUTPUT_TOKEN)
    log.tokens_used = input_tokens + output_tokens
    log.estimated_cost_usd = cost
    log.raw_ai_response = json.dumps(parsed) if parsed else None

    if not parsed:
        log.status = "failed"
        log.error_message = "Claude não retornou JSON válido."
        log.completed_at = datetime.now(timezone.utc)
        db.commit()
        return

    if not jurisdiction:
        jurisdiction = _find_or_create_jurisdiction(db, query, level)

    log.jurisdiction_id = jurisdiction.id
    is_refresh = jurisdiction.ceilings is not None and len(jurisdiction.ceilings) > 0
    _save_ceilings(db, jurisdiction, parsed, is_refresh=is_refresh)

    jurisdiction.last_researched = datetime.now(timezone.utc)
    jurisdiction.data_confidence = "ai_sourced"

    log.status = "completed"
    log.completed_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(f"Job {log_id} concluído. Tokens: {log.tokens_used}, Custo: ${cost:.5f}")


def _resolve_context(
    db: Session, query: str, jurisdiction_id: Optional[int]
) -> tuple[str, str, Optional[Jurisdiction]]:
    level = "municipal"
    state_context = ""
    jurisdiction = None

    if jurisdiction_id:
        jurisdiction = db.query(Jurisdiction).filter(Jurisdiction.id == jurisdiction_id).first()
        if jurisdiction:
            level = jurisdiction.level
            if jurisdiction.level == "municipal" and jurisdiction.state:
                state_context = f"\nEstado: {jurisdiction.state.name} ({jurisdiction.uf})"

    normalized = normalize(query)
    if normalized in ("federal", "uniao", "uniao federal"):
        level = "federal"
    elif len(normalized) == 2 and normalized.isalpha():
        level = "state"

    return level, state_context, jurisdiction


def _collect_search_results(query: str, level: str, state_context: str) -> str:
    """
    Faz até 3 buscas Tavily focadas e consolida os resultados.
    Tavily é grátis até 1.000 buscas/mês — não consome créditos Claude.
    """
    if not settings.tavily_api_key:
        return "Tavily não configurado — sem resultados de busca."

    queries = [
        f'teto RPV "{query}" lei requisição pequeno valor',
        f'"{query}" RPV legislação precatório',
    ]
    if level == "municipal":
        queries.append(f'lei municipal "{query}" RPV teto valor')

    all_snippets = []
    seen_urls = set()

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=settings.tavily_api_key)

        for q in queries[:2]:  # Máximo 2 buscas por pesquisa
            result = client.search(q, max_results=3, search_depth="basic")
            for r in result.get("results", []):
                url = r.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                snippet = f"URL: {url}\n{r.get('content', '')[:400]}"
                all_snippets.append(snippet)

    except Exception as e:
        return f"Erro Tavily: {str(e)}"

    return "\n\n---\n\n".join(all_snippets) if all_snippets else "Sem resultados de busca."


def _extract_with_claude(
    query: str, level: str, state_context: str, search_results: str
) -> tuple[Optional[dict], int, int]:
    """
    Chama Claude Haiku UMA VEZ com o conteúdo já coletado pelo Tavily.
    Sem tool_use — prompt direto → JSON direto.
    """
    prompt = EXTRACTION_PROMPT.format(
        jurisdiction_name=query,
        level=level,
        state_context=state_context,
        search_results=search_results[:6000],  # Limita contexto para economizar tokens
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model=RESEARCH_MODEL,
        max_tokens=1024,  # JSON de saída não precisa de mais que isso
        messages=[{"role": "user", "content": prompt}],
    )

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text
            break

    parsed = _parse_json_response(text)
    return parsed, response.usage.input_tokens, response.usage.output_tokens


def _save_municipal_cascade(
    db: Session, jurisdiction: Jurisdiction, state: Jurisdiction, log: ResearchLog
) -> None:
    """Marca município como seguindo o estado sem pesquisa de IA."""
    federal = db.query(Jurisdiction).filter(Jurisdiction.level == "federal").first()
    if federal and federal.ceilings:
        ref = federal.ceilings[0]
        c = RpvCeiling(
            jurisdiction_id=jurisdiction.id,
            valid_from=ref.valid_from,
            valid_until=ref.valid_until,
            ceiling_type=ref.ceiling_type,
            ceiling_value=ref.ceiling_value,
            ceiling_description=ref.ceiling_description,
            legislation_name=ref.legislation_name,
            legislation_url=ref.legislation_url,
            legislation_description=(
                f"Teto federal aplicado por ausência de lei local. {ref.legislation_description or ''}"
            ),
            uses_federal_fallback=True,
            confidence="ai_sourced",
            ai_research_notes=f"Herdado do estado {state.name} via cascade.",
        )
        db.add(c)
    jurisdiction.last_researched = datetime.now(timezone.utc)
    jurisdiction.data_confidence = "ai_sourced"
    log.jurisdiction_id = jurisdiction.id
    log.tokens_used = 0
    log.estimated_cost_usd = 0.0


def _parse_json_response(text: str) -> Optional[dict]:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _find_or_create_jurisdiction(db: Session, query: str, level: str) -> Jurisdiction:
    from app.services.normalizer import resolve_jurisdiction
    candidates = resolve_jurisdiction(db, query)
    if candidates:
        return candidates[0]
    j = Jurisdiction(
        level=level,
        name=query.strip().title(),
        search_aliases=[normalize(query)],
        data_confidence="ai_sourced",
    )
    db.add(j)
    db.flush()
    return j


def _save_ceilings(db: Session, jurisdiction: Jurisdiction, parsed: dict, is_refresh: bool = False) -> None:
    """
    Persiste os tetos no banco.

    is_refresh=True → é uma re-pesquisa de dados existentes:
      - Remove apenas o teto VIGENTE (valid_until = null) antes de inserir o novo
      - Mantém o histórico intacto (leis passadas não mudam)

    is_refresh=False → primeira pesquisa:
      - Insere tudo normalmente
    """
    from datetime import date

    if is_refresh:
        # Remove só o teto vigente, preserva histórico
        db.query(RpvCeiling).filter(
            RpvCeiling.jurisdiction_id == jurisdiction.id,
            RpvCeiling.valid_until == None,  # noqa: E711
        ).delete()
        db.flush()

    if parsed.get("uses_federal_fallback") and not parsed.get("ceilings"):
        federal = db.query(Jurisdiction).filter(Jurisdiction.level == "federal").first()
        if federal and federal.ceilings:
            ref = federal.ceilings[0]
            db.add(RpvCeiling(
                jurisdiction_id=jurisdiction.id,
                valid_from=ref.valid_from,
                valid_until=ref.valid_until,
                ceiling_type=ref.ceiling_type,
                ceiling_value=ref.ceiling_value,
                ceiling_description=ref.ceiling_description,
                legislation_name=ref.legislation_name,
                legislation_url=ref.legislation_url,
                legislation_description=(
                    f"Teto federal aplicado por ausência de lei local. {ref.legislation_description or ''}"
                ),
                uses_federal_fallback=True,
                confidence="ai_sourced",
                ai_research_notes=parsed.get("research_notes", ""),
            ))
        return

    for item in parsed.get("ceilings", []):
        try:
            valid_from = date.fromisoformat(item["valid_from"])
        except (KeyError, ValueError):
            continue

        valid_until = None
        raw_until = item.get("valid_until")
        if raw_until and raw_until not in ("null", "None", ""):
            try:
                valid_until = date.fromisoformat(raw_until)
            except ValueError:
                pass

        url = item.get("legislation_url") or None
        if url in ("não encontrada", "nao encontrada", "N/A", "null", "None"):
            url = None

        db.add(RpvCeiling(
            jurisdiction_id=jurisdiction.id,
            valid_from=valid_from,
            valid_until=valid_until,
            ceiling_type=item.get("ceiling_type", "unknown"),
            ceiling_value=item.get("ceiling_value"),
            ceiling_description=item.get("ceiling_description", ""),
            legislation_name=item.get("legislation_name", ""),
            legislation_url=url,
            legislation_description=item.get("legislation_description"),
            uses_federal_fallback=parsed.get("uses_federal_fallback", False),
            confidence="ai_sourced",
            ai_research_notes=parsed.get("research_notes", ""),
        ))
