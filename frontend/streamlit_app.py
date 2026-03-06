"""
Frontend Streamlit — Consulta de Tetos de RPV
Liberta Precatórios
"""

import os
import time
from datetime import datetime

import httpx
import pandas as pd
import streamlit as st

API_BASE = os.getenv("BACKEND_URL", "http://localhost:8001") + "/api/v1"

st.set_page_config(
    page_title="Teto RPV — Liberta",
    page_icon="⚖️",
    layout="centered",
)

st.title("Consulta de Teto RPV")
st.caption("Histórico completo de tetos de Requisição de Pequeno Valor para processos contra o poder público.")

tab_consulta, tab_dashboard, tab_historico = st.tabs(["Consulta", "Dashboard", "Histórico"])


# ── Helpers ───────────────────────────────────────────────────────────────────

LEVEL_LABELS = {"federal": "Federal", "state": "Estado", "municipal": "Município"}


def format_date(d) -> str:
    if not d:
        return "atual"
    if isinstance(d, str):
        from datetime import date
        d = date.fromisoformat(d)
    return d.strftime("%d/%m/%Y")


def format_brl(value) -> str:
    if value is None:
        return "—"
    return f"R$ {value:_.2f}".replace("_", ".")


def confidence_badge(confidence: str) -> str:
    badges = {
        "verified": "✅ Verificado",
        "ai_sourced": "Pesquisado por IA",
        "unknown": "Não verificado",
    }
    return badges.get(confidence, confidence)


def parse_brl(text: str):
    """Converte 'R$ 85.000,00' ou '85000.00' para float."""
    cleaned = text.strip().replace("R$", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def render_ceilings_table(ceilings: list[dict], query: str = ""):
    if not ceilings:
        st.warning("Nenhum teto encontrado para esta jurisdição.")
        return

    rows = []
    for c in ceilings:
        period = f"{format_date(c['valid_from'])} → {format_date(c['valid_until'])}"
        rows.append({
            "Vigência": period,
            "Teto RPV": c["ceiling_description"],
            "Equivalente em R$": format_brl(c.get("brl_equivalent")),
            "Legislação": c["legislation_name"],
            "Link": c.get("legislation_url") or "—",
            "Descrição": c.get("legislation_description") or "—",
            "Confiança": confidence_badge(c.get("confidence", "unknown")),
            "⚠️": "⚠️" if c.get("flagged_for_review") else "",
        })

    df = pd.DataFrame(rows)

    st.dataframe(
        df,
        column_config={
            "Link": st.column_config.LinkColumn("Link", display_text="Acessar lei ↗"),
            "Vigência": st.column_config.TextColumn("Vigência", width="medium"),
            "Teto RPV": st.column_config.TextColumn("Teto RPV", width="small"),
            "Equivalente em R$": st.column_config.TextColumn("Equivalente (R$)", width="small"),
            "Legislação": st.column_config.TextColumn("Legislação", width="large"),
            "Descrição": st.column_config.TextColumn("Descrição", width="large"),
            "Confiança": st.column_config.TextColumn("Confiança", width="medium"),
            "⚠️": st.column_config.TextColumn("", width="small"),
        },
        hide_index=True,
        use_container_width=True,
    )

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Exportar CSV",
        data=csv,
        file_name=f"teto_rpv_{query.lower().replace(' ', '_')}.csv",
        mime="text/csv",
    )


def render_inline_classifier(ceilings: list[dict], jurisdiction_name: str):
    """Seção inline de calculadora de enquadramento dentro da Consulta."""
    vigente = next((c for c in ceilings if not c.get("valid_until")), None)
    if not vigente or not vigente.get("brl_equivalent"):
        return

    st.divider()
    st.subheader("Calcular enquadramento")
    st.caption(
        "Informe o valor do crédito para saber se ele é RPV ou Precatório "
        f"perante **{jurisdiction_name}**."
    )

    col_val, col_btn = st.columns([3, 1])
    with col_val:
        valor_input = st.text_input(
            "Valor do crédito (R$)",
            placeholder="Ex: 85.000,00",
            label_visibility="collapsed",
            key="calc_valor_inline",
        )
    with col_btn:
        calc_btn = st.button("Calcular", type="secondary", use_container_width=True, key="calc_btn_inline")

    if calc_btn and valor_input:
        valor = parse_brl(valor_input)
        if valor is None or valor <= 0:
            st.error("Valor inválido. Use o formato: 85.000,00 ou 85000.00")
        else:
            teto = vigente["brl_equivalent"]
            is_rpv = valor <= teto
            diferenca = abs(teto - valor)

            if is_rpv:
                st.success(f"RPV — O crédito se enquadra como Requisição de Pequeno Valor")
            else:
                st.error(f"PRECATÓRIO — O crédito supera o teto de RPV")

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Valor do crédito", format_brl(valor))
            col_m2.metric("Teto RPV vigente", format_brl(teto))
            col_m3.metric(
                "Diferença",
                format_brl(diferenca),
                delta=f"{'abaixo' if is_rpv else 'acima'} do teto",
                delta_color="normal" if is_rpv else "inverse",
            )

            st.caption(
                f"Base legal: {vigente['legislation_name']} · "
                f"Vigência: {format_date(vigente['valid_from'])} → {format_date(vigente.get('valid_until'))}"
            )
            if vigente.get("legislation_url"):
                st.markdown(f"[Acessar legislação ↗]({vigente['legislation_url']})")

            if not is_rpv and diferenca / teto < 0.3:
                st.warning(
                    f"O crédito supera o teto em apenas {diferenca / teto:.1%}. "
                    "Verifique com o advogado do processo se é possível renunciar ao excedente "
                    "para viabilizar o enquadramento como RPV."
                )


def poll_research(job_id: str):
    """Faz polling do job de pesquisa assíncrona com spinner."""
    with st.spinner("Pesquisando legislação... isso pode levar até 60 segundos."):
        for _ in range(60):
            time.sleep(2)
            try:
                r = httpx.get(f"{API_BASE}/research-status/{job_id}", timeout=10)
                data = r.json()

                if data["status"] == "completed":
                    return data
                if data["status"] == "failed":
                    error = data.get("error", "Erro desconhecido")
                    if "credit balance" in error or "billing" in error.lower():
                        st.error(
                            "Créditos da API Anthropic esgotados. "
                            "Adicione créditos em console.anthropic.com → Billing."
                        )
                    else:
                        st.error(f"Pesquisa falhou: {error}")
                    return None
            except Exception as e:
                st.error(f"Erro ao verificar status: {e}")
                return None

    st.error("Tempo limite excedido. Tente novamente.")
    return None


def fetch_suggestions(q: str) -> list[dict]:
    """Busca sugestões de jurisdição enquanto o usuário digita."""
    if not q or len(q.strip()) < 2:
        return []
    try:
        r = httpx.get(
            f"{API_BASE}/jurisdictions",
            params={"q": q.strip(), "limit": 5},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def render_search_input(input_key: str, search_flag_key: str):
    """
    Renderiza o campo de busca com autocomplete.
    Retorna (query, do_search).

    Usa uma chave "_pending" para contornar a restrição do Streamlit:
    session_state de um widget com key= só pode ser modificado ANTES
    do widget ser renderizado. A chave pending é aplicada no início do
    próximo rerun, antes de criar o widget.
    """
    pending_key = f"{input_key}_pending"

    # Aplica seleção pendente de suggestion antes do widget renderizar
    if st.session_state.get(pending_key):
        st.session_state[input_key] = st.session_state[pending_key]
        st.session_state[pending_key] = None
        st.session_state[search_flag_key] = True

    # Inicializa estado se necessário
    if input_key not in st.session_state:
        st.session_state[input_key] = ""
    if search_flag_key not in st.session_state:
        st.session_state[search_flag_key] = False

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        st.text_input(
            "",
            placeholder="Município, estado ou 'Federal'...",
            label_visibility="collapsed",
            key=input_key,
        )
    with col_btn:
        btn_clicked = st.button("Consultar", type="primary", use_container_width=True)

    q = st.session_state[input_key].strip()

    # Sugestões de autocomplete (não mostra se busca já foi disparada)
    suggestions = fetch_suggestions(q)
    if suggestions and not st.session_state[search_flag_key]:
        sug_cols = st.columns(min(len(suggestions), 5))
        for i, s in enumerate(suggestions[:5]):
            uf = f" ({s['uf']})" if s.get("uf") else ""
            lbl = f"{s['name']}{uf}  ·  {LEVEL_LABELS.get(s['level'], s['level'])}"
            if sug_cols[i].button(lbl, key=f"{input_key}_sug_{s['id']}", use_container_width=True):
                # Grava em chave PENDENTE (não no widget diretamente)
                st.session_state[pending_key] = s["name"]
                st.rerun()

    # Determina se deve pesquisar
    do_search = btn_clicked or st.session_state[search_flag_key]
    if st.session_state[search_flag_key]:
        st.session_state[search_flag_key] = False
        q = st.session_state[input_key].strip()

    return q, do_search


# ── Aba 1: Consulta ───────────────────────────────────────────────────────────

with tab_consulta:
    query, do_search = render_search_input("q_consulta", "search_consulta")

    if do_search and query:
        try:
            response = httpx.get(f"{API_BASE}/search", params={"q": query}, timeout=15)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")

            if status == "found":
                j = data["jurisdiction"]
                level_str = LEVEL_LABELS.get(j["level"], j["level"].capitalize())
                uf_str = f" ({j['uf']})" if j.get("uf") else ""
                st.success(f"**{j['name']}{uf_str}** — {level_str}")

                col_conf, col_date = st.columns(2)
                with col_conf:
                    st.caption(confidence_badge(j.get("data_confidence", "unknown")))
                with col_date:
                    age = data.get("data_age_days")
                    if age is not None:
                        st.caption(f"Verificado há {age} dias")

                if data.get("stale_refresh_triggered"):
                    st.info(
                        f"Dados com mais de {age} dias — verificando se a legislação foi alterada "
                        "em background. Resultados atuais exibidos abaixo."
                    )

                ceilings = data.get("ceilings", [])
                render_ceilings_table(ceilings, query)
                render_inline_classifier(ceilings, j["name"])

            elif status == "ambiguous":
                st.warning(
                    f"Encontramos {len(data['candidates'])} jurisdições para **{query}**. "
                    "Selecione uma ou refine a busca:"
                )
                for candidate in data["candidates"]:
                    uf_str = f" ({candidate['uf']})" if candidate.get("uf") else ""
                    level_str = LEVEL_LABELS.get(candidate["level"], candidate["level"])
                    label = f"{candidate['name']}{uf_str} — {level_str}"
                    if st.button(label, key=f"candidate_{candidate['id']}"):
                        r2 = httpx.get(
                            f"{API_BASE}/search", params={"q": candidate["name"]}, timeout=15
                        )
                        d2 = r2.json()
                        if d2.get("status") == "found":
                            ceilings2 = d2.get("ceilings", [])
                            render_ceilings_table(ceilings2, candidate["name"])
                            render_inline_classifier(ceilings2, candidate["name"])

            elif status == "researching":
                job_id = data.get("job_id")
                st.info(data.get("message", "Pesquisando..."))
                if job_id:
                    result = poll_research(job_id)
                    if result and result.get("ceilings"):
                        j = result.get("jurisdiction", {})
                        if j:
                            st.success(f"**{j['name']}** encontrado!")
                        ceilings_r = result["ceilings"]
                        render_ceilings_table(ceilings_r, query)
                        render_inline_classifier(ceilings_r, j.get("name", query))

            elif status == "not_found":
                st.error("Jurisdição não encontrada. Verifique o nome e tente novamente.")

            else:
                st.error(f"Resposta inesperada da API: {data}")

        except httpx.HTTPStatusError as e:
            st.error(
                f"Erro na API ({e.response.status_code}). "
                "Verifique se o backend foi reiniciado após atualizações."
            )
        except httpx.ConnectError:
            st.error("Não foi possível conectar à API. Verifique se o servidor está rodando em localhost:8001")
        except Exception as e:
            st.error(f"Erro inesperado: {e}")

    elif do_search and not query:
        st.warning("Digite o nome de uma jurisdição para consultar.")

    st.divider()
    st.caption(
        "Dados verificados são revisados manualmente. Dados pesquisados por IA podem conter imprecisões — "
        "sempre confirme na legislação oficial antes de utilizar em processos."
    )

    with st.expander("Como usar"):
        st.markdown("""
        - Digite o nome de um **município**, **estado** ou **"Federal"**
        - Selecione nas sugestões ou pressione **Consultar** para pesquisa livre
        - O sistema retorna o histórico completo de tetos de RPV
        - Após o resultado, use a seção **Calcular enquadramento** para classificar um crédito específico como RPV ou Precatório
        - **Verificado**: dado revisado manualmente pela equipe Liberta
        - **Pesquisado por IA**: dado coletado automaticamente — confirme na fonte oficial
        """)


# ── Aba 2: Dashboard ──────────────────────────────────────────────────────────

with tab_dashboard:
    st.subheader("Dashboard de Uso")

    col_r, _ = st.columns([1, 4])
    with col_r:
        st.button("Atualizar", key="refresh_dashboard")

    try:
        r = httpx.get(f"{API_BASE}/admin/stats", timeout=15)
        r.raise_for_status()
        stats = r.json()

        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de pesquisas", stats["total_searches"])
        col2.metric("Concluídas", stats["completed"])
        col3.metric("Falhas", stats["failed"])
        col4.metric("Jurisdições com dados", stats["jurisdictions_researched"])

        col_tok, col_cost = st.columns(2)
        col_tok.metric("Tokens consumidos", f"{stats['total_tokens']:,}".replace(",", "."))
        col_cost.metric("Custo total estimado", f"US$ {stats['total_cost_usd']:.4f}")

        st.divider()

        # Atividade diária
        if stats.get("daily_activity"):
            st.subheader("Pesquisas por dia")
            try:
                daily_df = pd.DataFrame(stats["daily_activity"])
                daily_df = daily_df.sort_values("day")
                daily_df.columns = ["Data", "Pesquisas", "Custo (US$)"]
                st.bar_chart(daily_df.set_index("Data")["Pesquisas"])
                st.dataframe(
                    daily_df,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Custo (US$)": st.column_config.NumberColumn(format="$%.5f"),
                    },
                )
            except Exception as e:
                st.warning(f"Não foi possível renderizar atividade diária: {e}")

        st.divider()

        # Mudanças recentes de legislação
        st.subheader("Atualizações recentes de legislação")
        if stats.get("recent_ceiling_updates"):
            try:
                updates_df = pd.DataFrame(stats["recent_ceiling_updates"])
                updates_df["updated_at"] = pd.to_datetime(
                    updates_df["updated_at"], errors="coerce"
                ).dt.strftime("%d/%m/%Y %H:%M")
                updates_df.columns = ["Jurisdição", "UF", "Nível", "Teto", "Legislação", "Atualizado em"]
                st.dataframe(updates_df, hide_index=True, use_container_width=True)
            except Exception as e:
                st.warning(f"Não foi possível renderizar atualizações: {e}")
        else:
            st.info("Nenhuma atualização de legislação nos últimos 30 dias.")

        st.divider()

        # Pesquisa em massa — estados
        st.subheader("Pesquisa em massa — estados")
        st.caption(
            "Dispara pesquisa de IA para todos os estados que ainda não têm dados de teto. "
            "Cada pesquisa consome ~$0.003 em créditos Anthropic."
        )
        col_btn2, col_info2 = st.columns([2, 3])
        with col_btn2:
            trigger_btn = st.button("Pesquisar todos os estados", type="secondary")
        with col_info2:
            st.caption("Estados com dados existentes ou jobs em andamento são ignorados.")

        if trigger_btn:
            try:
                r2 = httpx.post(f"{API_BASE}/admin/trigger-state-research", timeout=30)
                r2.raise_for_status()
                result = r2.json()
                if result["triggered"] > 0:
                    st.success(
                        f"{result['triggered']} pesquisas disparadas em background. "
                        f"({result['skipped']} estados já tinham dados.)"
                    )
                    st.write("**Estados sendo pesquisados:**")
                    st.write(", ".join(result["states_triggered"]))
                else:
                    st.info(
                        f"Todos os {result['skipped']} estados já têm dados cadastrados."
                    )
            except httpx.HTTPStatusError as e:
                st.error(f"Erro na API ({e.response.status_code}).")
            except Exception as e:
                st.error(f"Erro ao disparar pesquisa: {e}")

        st.divider()

        # Log de pesquisas recentes
        if stats.get("recent_searches"):
            st.subheader("Log de pesquisas recentes")
            try:
                log_rows = []
                for s in stats["recent_searches"]:
                    started = s.get("started_at")
                    if started:
                        try:
                            data_str = datetime.fromisoformat(started).strftime("%d/%m/%Y %H:%M")
                        except Exception:
                            data_str = started[:16]
                    else:
                        data_str = "—"
                    log_rows.append({
                        "Query": s["query"],
                        "Status": s["status"],
                        "Tokens": s.get("tokens") or "—",
                        "Custo (US$)": f"${s['cost_usd']:.5f}" if s.get("cost_usd") else "—",
                        "Modelo": s.get("model") or "—",
                        "Data": data_str,
                    })
                log_df = pd.DataFrame(log_rows)
                st.dataframe(log_df, hide_index=True, use_container_width=True)
            except Exception as e:
                st.warning(f"Não foi possível renderizar log: {e}")

    except httpx.HTTPStatusError as e:
        st.error(
            f"Erro na API ({e.response.status_code}). "
            "O backend pode precisar ser reiniciado para carregar os endpoints de admin."
        )
    except httpx.ConnectError:
        st.error("Não foi possível conectar à API. Verifique se o servidor está rodando.")
    except Exception as e:
        st.error(f"Erro ao carregar dashboard: {e}")


# ── Aba 3: Histórico ──────────────────────────────────────────────────────────

with tab_historico:
    st.subheader("Jurisdições Pesquisadas")
    st.caption("Todas as jurisdições com dados coletados, ordenadas pela consulta mais recente.")

    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        st.button("Atualizar", key="refresh_history")

    try:
        r = httpx.get(f"{API_BASE}/admin/history", timeout=15)
        r.raise_for_status()
        items = r.json()

        if not items:
            st.info("Nenhuma jurisdição pesquisada ainda. Faça uma consulta na aba Consulta.")
        else:
            level_map = {"federal": "Federal", "state": "Estadual", "municipal": "Municipal"}

            rows = []
            for item in items:
                last = item.get("last_researched")
                if last:
                    try:
                        dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                        last_fmt = dt.strftime("%d/%m/%Y %H:%M")
                    except Exception:
                        last_fmt = last[:16]
                else:
                    last_fmt = "—"

                rows.append({
                    "Jurisdição": item["jurisdiction_name"],
                    "UF": item.get("uf") or "—",
                    "Nível": level_map.get(item["level"], item["level"]),
                    "Teto Vigente": item.get("teto_vigente") or "—",
                    "Equivalente R$": format_brl(item.get("valor_brl")),
                    "Legislação": item.get("legislation_name") or "—",
                    "Link": item.get("legislation_url") or "—",
                    "Confiança": confidence_badge(item.get("confidence", "unknown")),
                    "Última Pesquisa": last_fmt,
                })

            df = pd.DataFrame(rows)
            st.dataframe(
                df,
                column_config={
                    "Jurisdição": st.column_config.TextColumn("Jurisdição", width="medium"),
                    "UF": st.column_config.TextColumn("UF", width="small"),
                    "Nível": st.column_config.TextColumn("Nível", width="small"),
                    "Teto Vigente": st.column_config.TextColumn("Teto Vigente", width="medium"),
                    "Equivalente R$": st.column_config.TextColumn("Equivalente R$", width="small"),
                    "Legislação": st.column_config.TextColumn("Legislação", width="large"),
                    "Link": st.column_config.LinkColumn("Link", display_text="↗"),
                    "Confiança": st.column_config.TextColumn("Confiança", width="medium"),
                    "Última Pesquisa": st.column_config.TextColumn("Última Pesquisa", width="medium"),
                },
                hide_index=True,
                use_container_width=True,
            )

            st.caption(f"{len(rows)} jurisdição(ões) com dados coletados.")

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Exportar histórico CSV",
                data=csv,
                file_name="historico_teto_rpv.csv",
                mime="text/csv",
            )

    except httpx.HTTPStatusError as e:
        st.error(f"Erro na API ({e.response.status_code}).")
    except httpx.ConnectError:
        st.error("Não foi possível conectar à API. Verifique se o servidor está rodando em localhost:8001")
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")
