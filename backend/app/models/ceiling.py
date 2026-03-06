from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RpvCeiling(Base):
    __tablename__ = "rpv_ceilings"

    id: Mapped[int] = mapped_column(primary_key=True)
    jurisdiction_id: Mapped[int] = mapped_column(ForeignKey("jurisdictions.id"), nullable=False)

    # Período de vigência
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[Optional[date]] = mapped_column(Date)  # NULL = vigente atualmente

    # Valor do teto
    ceiling_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # fixed_brl | salary_multiple | unknown
    ceiling_value: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    ceiling_description: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # "60 salários mínimos"

    # Legislação
    legislation_name: Mapped[str] = mapped_column(Text, nullable=False)
    legislation_url: Mapped[Optional[str]] = mapped_column(Text)
    legislation_description: Mapped[Optional[str]] = mapped_column(Text)

    # Fallback constitucional
    uses_federal_fallback: Mapped[bool] = mapped_column(Boolean, default=False)

    # Qualidade do dado
    confidence: Mapped[str] = mapped_column(
        String(10), default="unknown"
    )  # verified | ai_sourced | unknown
    ai_research_notes: Mapped[Optional[str]] = mapped_column(Text)
    flagged_for_review: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    jurisdiction: Mapped["Jurisdiction"] = relationship(  # noqa: F821
        "Jurisdiction", back_populates="ceilings"
    )

    __table_args__ = (
        Index("idx_ceilings_jurisdiction", "jurisdiction_id"),
        Index("idx_ceilings_valid_from", "valid_from"),
    )

    def __repr__(self) -> str:
        return f"<RpvCeiling {self.jurisdiction_id} {self.valid_from}→{self.valid_until}>"
