from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ResearchLog(Base):
    __tablename__ = "research_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    jurisdiction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jurisdictions.id"))
    search_query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending | running | completed | failed | needs_review
    ai_model_used: Mapped[Optional[str]] = mapped_column(String(50))
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(8, 6))
    raw_ai_response: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(
        String(20), default="user_query"
    )  # user_query | manual_seed | scheduled
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<ResearchLog {self.id} {self.status}>"
