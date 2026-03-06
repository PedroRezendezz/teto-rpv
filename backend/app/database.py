from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def enable_pg_trgm(db):
    """Ativa extensão de fuzzy search no PostgreSQL."""
    db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    db.commit()
