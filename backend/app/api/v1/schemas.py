from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel


class JurisdictionOut(BaseModel):
    id: int
    level: str
    name: str
    uf: Optional[str]
    ibge_code: Optional[str]
    data_confidence: str
    last_researched: Optional[datetime]

    model_config = {"from_attributes": True}


class CeilingOut(BaseModel):
    id: int
    valid_from: date
    valid_until: Optional[date]
    ceiling_description: str
    ceiling_type: str
    ceiling_value: Optional[float]
    brl_equivalent: Optional[float]
    legislation_name: str
    legislation_url: Optional[str]
    legislation_description: Optional[str]
    uses_federal_fallback: bool
    confidence: str
    flagged_for_review: bool

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    status: str  # found | ambiguous | not_found | researching
    jurisdiction: Optional[JurisdictionOut] = None
    candidates: list[JurisdictionOut] = []
    ceilings: list[CeilingOut] = []
    job_id: Optional[str] = None
    message: Optional[str] = None
    # Campos de atualização
    stale_refresh_triggered: bool = False   # True = atualização silenciosa em andamento
    data_age_days: Optional[int] = None     # Quantos dias desde a última verificação


class HistoryItem(BaseModel):
    jurisdiction_id: int
    jurisdiction_name: str
    level: str
    uf: Optional[str] = None
    teto_vigente: Optional[str] = None
    valor_brl: Optional[float] = None
    legislation_name: Optional[str] = None
    legislation_url: Optional[str] = None
    confidence: Optional[str] = None
    uses_federal_fallback: Optional[bool] = None
    last_researched: Optional[datetime] = None


class ResearchStatusResponse(BaseModel):
    job_id: str
    status: str  # pending | running | completed | failed
    jurisdiction: Optional[JurisdictionOut] = None
    ceilings: list[CeilingOut] = []
    error: Optional[str] = None
