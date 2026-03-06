from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import search, research, jurisdictions, admin

app = FastAPI(
    title="Teto RPV API",
    description="Sistema de consulta de tetos de RPV - Liberta",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restringir em produção
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "teto-rpv"}


app.include_router(search.router, prefix="/api/v1", tags=["Busca"])
app.include_router(research.router, prefix="/api/v1", tags=["Pesquisa IA"])
app.include_router(jurisdictions.router, prefix="/api/v1", tags=["Jurisdições"])
app.include_router(admin.router, prefix="/api/v1", tags=["Admin"])
