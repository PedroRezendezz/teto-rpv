"""
Frontend Streamlit — Consulta de Tetos de RPV
Liberta Precatórios
"""

import time

import httpx
import pandas as pd
import streamlit as st

API_BASE = "http://localhost:8001/api/v1"

st.set_page_config(
    page_title="Teto RPV — Liberta",
    page_icon="⚖️",
    layout="centered",
)

st.title("⚖️ Consulta de Teto RPV")
st.caption("Histórico completo de tetos de Requisição de Pequeno Valor para processos contra o poder público.")

tab_consulta, tab_historico = st.tabs(["🔍 Consulta", "📋 Histórico de Pesquisas"])


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
        "ai_sourced": "🤖 Pesquisado por IA",
        "unknown": "❓ Não verificado",
    }
    return badges.get(confidence, confidence)


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
        label="⬇️ Exportar CSV",
        data=csv,
        file_name=f"teto_rpv_{query.lower().replace(' ', '_')}.csv",
        mime="text/csv",
    )


def poll_research(job_id: str):
    """Faz polling do job de pesquisa assíncrona com spinner."""
    with st.spinner("🔍 Pesquisando legislação... isso pode levar até 60 segundos."):
        for _ in range(60):  # timeout de 60s
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
                            "⚠️ Créditos da API Anthropic esgotados. "
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


# ── Aba 1: Consulta ───────────────────────────────────────────────────────────

with tab_consulta:
    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input(
            label="Jurisdição",
            placeholder="Ex: São Paulo, Goiás, Campinas, Federal...",
            label_visibility="collapsed",
        )
    with col2:
        buscar = st.button("Consultar", use_container_width=True, type="primary")

    if buscar and query:
        try:
            response = httpx.get(f"{API_BASE}/search", params={"q": query}, timeout=15)
            data = response.json()

            status = data.get("status")

            if status == "found":
                j = data["jurisdiction"]
                st.success(f"**{j['name']}** — {j['level'].capitalize()} | {j.get('uf', '')}")

                col_conf, col_date = st.columns(2)
                with col_conf:
                    st.caption(confidence_badge(j.get("data_confidence", "unknown")))
                with col_date:
                    age = data.get("data_age_days")
                    if age is not None:
                        st.caption(f"Verificado há {age} dias")

                if data.get("stale_refresh_triggered"):
                    st.info(
                        f"🔄 Dados com mais de {age} dias — verificando se a legislação foi alterada "
                        "em background. Resultados atuais exibidos abaixo."
                    )

                render_ceilings_table(data.get("ceilings", []), query)

            elif status == "ambiguous":
                st.warning(f"Encontramos {len(data['candidates'])} jurisdições para **{query}**. Selecione uma:")
                for candidate in data["candidates"]:
                    label = f"{candidate['name']} ({candidate['level']}"
                    if candidate.get("uf"):
                        label += f" — {candidate['uf']}"
                    label += ")"
                    if st.button(label, key=f"candidate_{candidate['id']}"):
                        r2 = httpx.get(f"{API_BASE}/search", params={"q": candidate["name"]}, timeout=15)
                        d2 = r2.json()
                        if d2.get("status") == "found":
                            render_ceilings_table(d2.get("ceilings", []), candidate["name"])

            elif status == "researching":
                job_id = data.get("job_id")
                st.info(data.get("message", "Pesquisando..."))
                if job_id:
                    result = poll_research(job_id)
                    if result and result.get("ceilings"):
                        j = result.get("jurisdiction", {})
                        if j:
                            st.success(f"**{j['name']}** encontrado!")
                        render_ceilings_table(result["ceilings"], query)

            elif status == "not_found":
                st.error("Jurisdição não encontrada. Verifique o nome e tente novamente.")

            else:
                st.error(f"Resposta inesperada da API: {data}")

        except httpx.ConnectError:
            st.error("⚠️ Não foi possível conectar à API. Verifique se o servidor está rodando em localhost:8001")
        except Exception as e:
            st.error(f"Erro inesperado: {e}")

    elif buscar and not query:
        st.warning("Digite o nome de uma jurisdição para consultar.")

    st.divider()
    st.caption(
        "ℹ️ Dados verificados são revisados manualmente. Dados pesquisados por IA podem conter imprecisões — "
        "sempre confirme na legislação oficial antes de utilizar em processos."
    )

    with st.expander("ℹ️ Como usar"):
        st.markdown("""
        - Digite o nome de um **município**, **estado** ou **"Federal"**
        - O sistema retorna o histórico completo de tetos de RPV em ordem decrescente
        - **✅ Verificado**: dado revisado manualmente pela equipe Liberta
        - **🤖 Pesquisado por IA**: dado coletado automaticamente — confirme na fonte oficial
        - Se o município não estiver no banco, uma pesquisa será disparada automaticamente (até 60s)
        - Use o botão **Exportar CSV** para salvar os dados
        """)


# ── Aba 2: Histórico ──────────────────────────────────────────────────────────

with tab_historico:
    st.subheader("Jurisdições Pesquisadas")
    st.caption("Todas as jurisdições com dados coletados, ordenadas pela consulta mais recente.")

    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        st.button("🔄 Atualizar", key="refresh_history")

    try:
        r = httpx.get(f"{API_BASE}/admin/history", timeout=15)
        items = r.json()

        if not items:
            st.info("Nenhuma jurisdição pesquisada ainda. Faça uma consulta na aba 🔍 Consulta.")
        else:
            level_map = {"federal": "Federal", "state": "Estadual", "municipal": "Municipal"}

            rows = []
            for item in items:
                last = item.get("last_researched")
                if last:
                    from datetime import datetime
                    dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    last_fmt = dt.strftime("%d/%m/%Y %H:%M")
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
                label="⬇️ Exportar histórico CSV",
                data=csv,
                file_name="historico_teto_rpv.csv",
                mime="text/csv",
            )

    except httpx.ConnectError:
        st.error("⚠️ Não foi possível conectar à API. Verifique se o servidor está rodando em localhost:8001")
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")
