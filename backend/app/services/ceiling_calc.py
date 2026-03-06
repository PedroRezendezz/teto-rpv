"""
Calcula equivalência em R$ para tetos expressos em salários mínimos.
"""

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.minimum_salary import MinimumSalary


def get_minimum_salary_on_date(db: Session, reference_date: date) -> Optional[float]:
    """Retorna o valor do salário mínimo vigente na data informada."""
    record = (
        db.query(MinimumSalary)
        .filter(
            MinimumSalary.valid_from <= reference_date,
            (MinimumSalary.valid_until == None) | (MinimumSalary.valid_until >= reference_date),
        )
        .order_by(MinimumSalary.valid_from.desc())
        .first()
    )
    return float(record.value_brl) if record else None


def get_current_minimum_salary(db: Session) -> Optional[float]:
    return get_minimum_salary_on_date(db, date.today())


def calculate_brl_equivalent(
    db: Session,
    ceiling_type: str,
    ceiling_value: Optional[float],
    reference_date: Optional[date] = None,
) -> Optional[float]:
    """
    Converte o teto para R$ com base no salário mínimo da data de referência.
    Usa data atual se reference_date não for informado.
    """
    if ceiling_type == "fixed_brl" and ceiling_value:
        return float(ceiling_value)

    if ceiling_type == "salary_multiple" and ceiling_value:
        ref = reference_date or date.today()
        minimum = get_minimum_salary_on_date(db, ref)
        if minimum:
            return round(float(ceiling_value) * minimum, 2)

    return None
