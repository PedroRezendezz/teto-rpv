# Teto RPV — Sistema de Consulta de Tetos de RPV

Sistema que permite consultar o histórico completo de tetos de RPV (Requisição de Pequeno Valor) para processos contra o poder público nas esferas federal, estadual e municipal.

## Stack

- **Backend:** FastAPI + SQLAlchemy + PostgreSQL
- **Frontend:** Streamlit
- **IA:** Claude (Anthropic) + Tavily (busca web)
- **Hosting:** Railway.app + Neon.tech (PostgreSQL)

---

## Setup local

### 1. Pré-requisitos

- Python 3.11+
- PostgreSQL local ou conta no [Neon.tech](https://neon.tech) (free tier)
- Chave de API da [Anthropic](https://console.anthropic.com)
- Chave de API do [Tavily](https://tavily.com) (free tier)

### 2. Instalar dependências

```bash
# Instalar uv (gerenciador de pacotes)
pip install uv

# Clonar e entrar no projeto
cd teto-rpv

# Instalar dependências
uv pip install -e .
```

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com suas credenciais
```

Exemplo de `.env`:
```
DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/teto_rpv?sslmode=require
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
```

### 4. Criar banco e rodar migrations

```bash
cd backend

# Rodar migration inicial (cria todas as tabelas + ativa pg_trgm)
DATABASE_URL=<sua-url> alembic upgrade head
```

### 5. Popular dados base

```bash
cd backend

# Popula: salário mínimo histórico + Federal (verificado) + 27 estados
DATABASE_URL=<sua-url> python -m scripts.seed

# Importa todas as 5.570 cidades do IBGE (via API pública)
DATABASE_URL=<sua-url> python -m scripts.import_ibge
```

### 6. Rodar o backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Acesse a documentação automática: http://localhost:8000/docs

### 7. Rodar o frontend

```bash
cd frontend
streamlit run streamlit_app.py
```

Acesse: http://localhost:8501

---

## Custos de API

### Modelo de custo

O sistema usa **Claude Haiku** (o modelo mais barato da Anthropic) combinado com **Tavily** (busca gratuita) para minimizar gastos.

| Componente | Custo | Observação |
|---|---|---|
| Tavily (busca web) | **Grátis** | Até 1.000 buscas/mês no free tier |
| Claude Haiku (extração) | ~$0.003/pesquisa | $0.80/M tokens input, $4.00/M tokens output |
| Cache hit (dado já no banco) | **$0.00** | Sem chamada de IA |

### Quando ocorre custo

O custo de IA só é gerado em dois casos:

1. **Cache miss** — primeiro acesso a uma jurisdição (município/estado) que ainda não está no banco
2. **Refresh automático** — dados com mais de 90 dias são re-verificados silenciosamente em background

Consultas repetidas à mesma jurisdição **não geram custo** — o resultado já está no cache.

### Estimativas práticas

| Cenário | Custo estimado |
|---|---|
| 1 município novo | ~$0.003 |
| 20 municípios novos | ~$0.06 |
| 100 municípios novos | ~$0.30 |
| Com $5 (Anthropic credits) | ~1.500 municípios novos |
| Com $5 + state cascade¹ | ~3.000–4.000 municípios |

¹ **State cascade:** municípios cujo estado já usa o teto federal são marcados automaticamente sem chamada de IA (custo $0).

### Ciclo de atualização (staleness)

- Dados são considerados "stale" (desatualizados) após **90 dias** sem re-verificação
- Quando um dado stale é consultado, o sistema retorna o cache imediatamente e dispara uma re-pesquisa em background — o usuário não espera
- Dados históricos (`valid_until != null`) **nunca** são re-pesquisados (legislação passada não muda)
- Apenas o teto vigente (`valid_until = null`) é sujeito ao ciclo de atualização

---

## Endpoints principais

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/health` | Status do serviço |
| GET | `/api/v1/search?q={query}` | Busca principal |
| GET | `/api/v1/research-status/{id}` | Status de pesquisa IA |
| GET | `/api/v1/jurisdictions` | Lista jurisdições (autocomplete) |
| GET | `/api/v1/admin/history` | Histórico de todas as jurisdições pesquisadas |

### Exemplo de resposta `/search`

```json
{
  "status": "found",
  "jurisdiction": {
    "name": "Goiás",
    "level": "state",
    "uf": "GO"
  },
  "ceilings": [
    {
      "valid_from": "2025-01-01",
      "valid_until": null,
      "ceiling_description": "10 salários mínimos",
      "legislation_name": "Lei Estadual nº 21.823/2024",
      "legislation_url": "https://...",
      "legislation_description": "Reduz teto de RPV do Estado de Goiás para 10 SM",
      "confidence": "ai_sourced"
    }
  ]
}
```

---

## Arquitetura

```
Usuário → Streamlit → FastAPI → PostgreSQL (cache)
                             ↓ (cache miss)
                       Claude + Tavily → grava no DB → retorna
```

- **Cache-hit:** retorno imediato, sem custo de IA
- **Cache-miss:** pesquisa assíncrona (~30-60s), resultado armazenado permanentemente

---

## Estrutura do projeto

```
teto-rpv/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Configurações (env vars)
│   │   ├── database.py          # SQLAlchemy engine
│   │   ├── models/              # ORM models
│   │   ├── api/v1/              # Endpoints
│   │   └── services/            # Lógica de negócio
│   ├── scripts/                 # Seed e import
│   └── alembic/                 # Migrations
├── frontend/
│   └── streamlit_app.py
├── data/
│   └── seed_data/               # JSONs de dados base
└── pyproject.toml
```

---

## Deploy (Railway.app)

1. Crie conta em [railway.app](https://railway.app)
2. Novo projeto → Deploy from GitHub
3. Adicione variáveis de ambiente no painel
4. O `Procfile` ou `railway.json` não é necessário — Railway detecta FastAPI automaticamente

Para o Streamlit, crie um segundo serviço no mesmo projeto apontando para `/frontend`.
