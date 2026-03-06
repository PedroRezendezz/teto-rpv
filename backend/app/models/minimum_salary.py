from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MinimumSalary(Base):
    __tablename__ = "minimum_salary_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[Optional[date]] = mapped_column(Date)  # NULL = vigente
    value_brl: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    legislation: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<MinimumSalary R${self.value_brl} from {self.valid_from}>"
