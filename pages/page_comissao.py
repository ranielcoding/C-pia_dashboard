import streamlit as st
import pandas as pd
import io
from datetime import datetime, date, timedelta
from cache_loaders import (
    carregar_comissao,
    clear_loader_cache,
    get_cache_key_comissao,
    load_if_cache_ready,
)
from ui_theme import apply_dashboard_theme, page_header
from ui_formatting import format_brl, format_pt_number

apply_dashboard_theme()


def renderizar_pagina_comissao():
    page_header("Comissão por Promotor de Vendas", "Resumo dos valores faturados e comissões por promotor.", icon="🤝")

    # --- 1. SELEÇÃO DE PERÍODO ---
    col1, col2 = st.columns(2)
    with col1:
        data_inicio = st.date_input(
            "Data inicial",
            value=datetime.now().date().replace(day=1),
            format="DD/MM/YYYY"
        )
    with col2:
        data_fim = st.date_input(
            "Data final",
            value=datetime.now().date(),
            format="DD/MM/YYYY"
        )

    # Valida se a data final é maior ou igual à inicial
    if data_inicio > data_fim:
        st.error("A data final deve ser maior ou igual à data inicial.")
        return

    st.info(f"📅 **Período selecionado:** {data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}")

    if st.button("🔄 Atualizar Dados"):
        clear_loader_cache(carregar_comissao, "carregar_comissao")
        st.session_state["_comissao_ready"] = True
        st.rerun()
    cache_key = get_cache_key_comissao(data_inicio, data_fim)
    df = load_if_cache_ready(
        carregar_comissao,
        "carregar_comissao",
        cache_key,
        force=st.session_state.pop("_comissao_ready", False),
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    if df is None:
        st.info("Os dados ainda não estão no cache. Aguarde o aquecimento ou clique em 'Atualizar Dados'.")
        return

    if df is not None and not df.empty:
        # --- 2. DEMAIS FILTROS (baseados nos dados do período) ---
        # Usa a mesma chave 'filtro_supervisor' do page_setores para herdar
        # automaticamente o supervisor definido no login.
        if 'filtro_supervisor' not in st.session_state:
            st.session_state['filtro_supervisor'] = []

        col_sup, col_prom = st.columns(2)

        with col_sup:
            supervisores = sorted(df['Supervisor'].unique())
            # Remove eventuais valores do login que não existam na base atual
            st.session_state['filtro_supervisor'] = [
                v for v in st.session_state['filtro_supervisor'] if v in supervisores
            ]
            filtro_sup = st.multiselect(
                "SUPERVISOR",
                supervisores,
                key='filtro_supervisor',
                placeholder="(Todos)",
            )

        with col_prom:
            if filtro_sup:
                promotores_disponiveis = sorted(
                    df[df['Supervisor'].isin(filtro_sup)]['Promotor'].unique()
                )
            else:
                promotores_disponiveis = sorted(df['Promotor'].unique())
            filtro_prom = st.multiselect("PROMOTOR DE VENDAS", promotores_disponiveis, placeholder="(Todos)")

        # Aplica os filtros de supervisor/promotor
        df_filtrado = df.copy()
        if filtro_sup:
            df_filtrado = df_filtrado[df_filtrado['Supervisor'].isin(filtro_sup)]
        if filtro_prom:
            df_filtrado = df_filtrado[df_filtrado['Promotor'].isin(filtro_prom)]

        st.divider()

        # --- 3. PREPARAÇÃO DO DATAFRAME DE EXIBIÇÃO ---
        df_exibicao = df_filtrado[['Promotor', 'Valor_Faturado', 'Valor_Comissao', 'Percentual_Medio']].copy()
        df_exibicao.columns = ['Promotor', 'Valor Faturado', 'Valor Comissão', 'Percentual (Médio)']
        tabela_exibicao = df_exibicao.copy()
        tabela_exibicao["Valor Faturado"] = tabela_exibicao["Valor Faturado"].map(format_brl)
        tabela_exibicao["Valor Comissão"] = tabela_exibicao["Valor Comissão"].map(format_brl)
        tabela_exibicao["Percentual (Médio)"] = tabela_exibicao[
            "Percentual (Médio)"
        ].map(lambda value: f"{format_pt_number(value, decimals=2)}%")

        # Linha com título e botão de download
        c1, c2 = st.columns([3, 1])
        with c1:
            st.subheader("Resumo de Comissões")
        with c2:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_exibicao.to_excel(writer, index=False, sheet_name='Comissao')
            st.download_button(
                label="📥 Baixar Excel",
                data=buffer.getvalue(),
                file_name="relatorio_comissao.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch"
            )

        st.dataframe(
            tabela_exibicao,
            width="stretch",
            hide_index=True,
            height=600,
            lazy=True,
            alt="Comissões de vendas por promotor, faturamento e percentual médio",
            column_config={"Promotor": st.column_config.TextColumn("Promotor", width="large")}
        )

        st.caption(
            f"**Totais Filtrados** — "
            f"Faturado: {format_brl(df_filtrado['Valor_Faturado'].sum())} | "
            f"Comissão: {format_brl(df_filtrado['Valor_Comissao'].sum())}"
        )

    else:
        st.warning("Nenhum dado retornado ou ocorreu um erro na consulta.")

if __name__ == "__main__":
    renderizar_pagina_comissao()