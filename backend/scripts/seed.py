"""
Script principal de seed — popula o banco com dados base.

Uso:
    cd backend
    python -m scripts.seed

Popula:
1. Salário mínimo histórico (2005-hoje)
2. Jurisdição federal + tetos históricos EC 62, EC 94, EC 113
3. Todas as jurisdições estaduais (sem tetos — serão pesquisados por IA)
"""

import json
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import SessionLocal, engine
from app.models import Jurisdiction, MinimumSalary, RpvCeiling
from app.database import Base

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seed_data")


def seed_minimum_salary(db):
    print("→ Populando salário mínimo histórico...")
    count = db.query(MinimumSalary).count()
    if count > 0:
        print(f"  Já existem {count} registros. Pulando.")
        return

    with open(os.path.join(DATA_DIR, "minimum_salary.json"), encoding="utf-8") as f:
        records = json.load(f)

    for r in records:
        ms = MinimumSalary(
            valid_from=date.fromisoformat(r["valid_from"]),
            valid_until=date.fromisoformat(r["valid_until"]) if r["valid_until"] else None,
            value_brl=r["value_brl"],
            legislation=r.get("legislation"),
        )
        db.add(ms)

    db.commit()
    print(f"  ✓ {len(records)} registros inseridos.")


def seed_federal(db):
    print("→ Populando jurisdição federal...")
    existing = db.query(Jurisdiction).filter(Jurisdiction.level == "federal").first()
    if existing:
        print(f"  Já existe: {existing.name}. Pulando.")
        return

    with open(os.path.join(DATA_DIR, "federal.json"), encoding="utf-8") as f:
        data = json.load(f)

    j_data = data["jurisdiction"]
    j = Jurisdiction(
        level=j_data["level"],
        name=j_data["name"],
        search_aliases=j_data["search_aliases"],
        data_confidence="verified",
        last_researched=datetime.now(timezone.utc),
    )
    db.add(j)
    db.flush()

    for ceiling_data in data["ceilings"]:
        c = RpvCeiling(
            jurisdiction_id=j.id,
            valid_from=date.fromisoformat(ceiling_data["valid_from"]),
            valid_until=(
                date.fromisoformat(ceiling_data["valid_until"])
                if ceiling_data["valid_until"]
                else None
            ),
            ceiling_type=ceiling_data["ceiling_type"],
            ceiling_value=ceiling_data["ceiling_value"],
            ceiling_description=ceiling_data["ceiling_description"],
            legislation_name=ceiling_data["legislation_name"],
            legislation_url=ceiling_data["legislation_url"],
            legislation_description=ceiling_data["legislation_description"],
            confidence="verified",
        )
        db.add(c)

    db.commit()
    print(f"  ✓ Federal criado com {len(data['ceilings'])} períodos.")


def seed_states(db):
    print("→ Populando estados...")
    with open(os.path.join(DATA_DIR, "states.json"), encoding="utf-8") as f:
        states = json.load(f)

    created = 0
    skipped = 0
    for s in states:
        existing = db.query(Jurisdiction).filter(
            Jurisdiction.level == "state",
            Jurisdiction.uf == s["uf"],
        ).first()
        if existing:
            skipped += 1
            continue

        j = Jurisdiction(
            level="state",
            name=s["name"],
            uf=s["uf"],
            search_aliases=s["search_aliases"],
            data_confidence="unknown",
        )
        db.add(j)
        created += 1

    db.commit()
    print(f"  ✓ {created} estados criados, {skipped} já existiam.")


def main():
    print("=== SEED: Teto RPV ===\n")
    Base.metadata.create_all(bind=engine)  # garante tabelas criadas
    db = SessionLocal()
    try:
        seed_minimum_salary(db)
        seed_federal(db)
        seed_states(db)
        print("\n✓ Seed concluído com sucesso.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
