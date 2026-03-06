"""
Importa todas as 5.570 cidades do IBGE para a tabela jurisdictions.

O arquivo CSV deve ser baixado de:
https://www.ibge.gov.br/explica/codigos-dos-municipios.php

Ou via API do IBGE:
https://servicodados.ibge.gov.br/api/v1/localidades/municipios

Uso:
    cd backend
    python -m scripts.import_ibge

O script busca automaticamente da API do IBGE se não houver CSV local.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
from sqlalchemy.orm import Session
from unidecode import unidecode

from app.database import SessionLocal
from app.models.jurisdiction import Jurisdiction


def normalize(s: str) -> str:
    import re
    return re.sub(r"\s+", " ", unidecode(s).lower().strip())


def fetch_from_ibge_api() -> list[dict]:
    print("→ Buscando municípios da API do IBGE...")
    url = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
    response = httpx.get(url, timeout=60)
    response.raise_for_status()
    return response.json()


def get_or_create_state(db: Session, uf: str, state_name: str) -> Jurisdiction:
    state = db.query(Jurisdiction).filter(
        Jurisdiction.level == "state",
        Jurisdiction.uf == uf,
    ).first()
    if not state:
        state = Jurisdiction(
            level="state",
            name=state_name,
            uf=uf,
            search_aliases=[normalize(state_name), uf.lower()],
            data_confidence="unknown",
        )
        db.add(state)
        db.flush()
    return state


def import_municipalities(db: Session, municipalities: list[dict]) -> None:
    print(f"→ Importando {len(municipalities)} municípios...")

    # Pré-carrega estados existentes
    state_cache: dict[str, Jurisdiction] = {}

    batch_size = 500
    created = 0
    skipped = 0

    for i, mun in enumerate(municipalities):
        ibge_code = str(mun["id"])
        name = mun["nome"]

        # Alguns municípios da API IBGE retornam microrregiao null
        microrregiao = mun.get("microrregiao")
        if not microrregiao or not microrregiao.get("mesorregiao"):
            skipped += 1
            continue
        uf = microrregiao["mesorregiao"]["UF"]["sigla"]
        state_name = microrregiao["mesorregiao"]["UF"]["nome"]

        # Verifica se já existe
        existing = db.query(Jurisdiction).filter(
            Jurisdiction.ibge_code == ibge_code
        ).first()
        if existing:
            skipped += 1
            continue

        # Garante estado no cache
        if uf not in state_cache:
            state_cache[uf] = get_or_create_state(db, uf, state_name)

        state = state_cache[uf]

        # Cria município
        aliases = [normalize(name)]
        # Adiciona variantes sem sufixos comuns
        for suffix in [" de", " do", " da", " dos", " das"]:
            clean = normalize(name).replace(suffix + " ", " ")
            if clean != aliases[0]:
                aliases.append(clean)

        j = Jurisdiction(
            level="municipal",
            name=name,
            uf=uf,
            ibge_code=ibge_code,
            state_id=state.id,
            search_aliases=list(set(aliases)),
            data_confidence="unknown",
        )
        db.add(j)
        created += 1

        # Commit em lotes
        if (i + 1) % batch_size == 0:
            db.commit()
            print(f"  {i + 1}/{len(municipalities)} processados...")

    db.commit()
    print(f"  ✓ {created} municípios criados, {skipped} já existiam.")


def main():
    print("=== IMPORT IBGE: Municípios ===\n")

    municipalities = fetch_from_ibge_api()

    db = SessionLocal()
    try:
        import_municipalities(db, municipalities)
        print("\n✓ Import concluído.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
