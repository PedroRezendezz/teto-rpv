"""
Normalização e resolução de inputs de jurisdição.

Responsável por converter strings livres do usuário ("são paulo", "SP", "sampa")
em registros da tabela jurisdictions — sem custo de API.
"""

import re
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session
from unidecode import unidecode

from app.models.jurisdiction import Jurisdiction


def normalize(raw: str) -> str:
    """Remove acentos, lowercase e espaços extras."""
    return re.sub(r"\s+", " ", unidecode(raw).lower().strip())


def resolve_jurisdiction(db: Session, query: str) -> list[Jurisdiction]:
    """
    Tenta resolver uma string de busca para uma ou mais jurisdições.

    Ordem de tentativas:
    1. Match exato no campo name (case-insensitive)
    2. Match exato em qualquer alias
    3. Match de UF (ex: "SP" → estado de São Paulo)
    4. Fuzzy match via pg_trgm (similaridade > 0.3)

    Retorna lista: vazia = não encontrado, >1 = ambíguo (pede confirmação).
    """
    normalized = normalize(query)

    # 1. Match exato por nome
    result = db.query(Jurisdiction).filter(
        func.lower(Jurisdiction.name) == normalized
    ).all()
    if result:
        return result

    # 2. Match por alias
    result = db.query(Jurisdiction).filter(
        Jurisdiction.search_aliases.any(normalized)
    ).all()
    if result:
        return result

    # 3. Match por UF (2 letras → retorna o estado)
    if len(normalized) == 2 and normalized.isalpha():
        result = db.query(Jurisdiction).filter(
            func.lower(Jurisdiction.uf) == normalized,
            Jurisdiction.level == "state",
        ).all()
        if result:
            return result

    # 4. "federal" → jurisdição federal
    if normalized in ("federal", "uniao", "uniao federal", "governo federal"):
        result = db.query(Jurisdiction).filter(Jurisdiction.level == "federal").all()
        if result:
            return result

    # 5. Fuzzy match por pg_trgm
    result = (
        db.query(Jurisdiction)
        .filter(
            text("similarity(lower(name), :q) > 0.3").bindparams(q=normalized)
        )
        .order_by(text("similarity(lower(name), :q) DESC").bindparams(q=normalized))
        .limit(5)
        .all()
    )
    return result
