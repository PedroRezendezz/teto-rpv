from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(10))  # federal | state | municipal
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    uf: Mapped[Optional[str]] = mapped_column(String(2))
    ibge_code: Mapped[Optional[str]] = mapped_column(String(7), unique=True)
    state_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jurisdictions.id"))
    search_aliases: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    data_confidence: Mapped[str] = mapped_column(String(10), default="unknown")
    last_researched: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    state: Mapped[Optional["Jurisdiction"]] = relationship(
        "Jurisdiction", remote_side="Jurisdiction.id", foreign_keys=[state_id]
    )
    ceilings: Mapped[list["RpvCeiling"]] = relationship(  # noqa: F821
        "RpvCeiling", back_populates="jurisdiction", order_by="RpvCeiling.valid_from.desc()"
    )

    __table_args__ = (
        Index("idx_jurisdictions_level", "level"),
        Index("idx_jurisdictions_uf", "uf"),
        Index("idx_jurisdictions_name_lower", func.lower(name)),
    )

    def __repr__(self) -> str:
        return f"<Jurisdiction {self.level}:{self.name}>"
