import streamlit as st
import pandas as pd
import threading
import io
from cache_loaders import (
    carregar_positivacao,
    get_scoped_cache_key,
    get_active_cache_version,
    load_if_cache_ready,
    trigger_warm,
)
from ui_theme import apply_dashboard_theme, page_header
from ui_formatting import format_brl

apply_dashboard_theme()
page_header("Positivação Geral", "Resumo dos indicadores de positivação por área.", icon="📈")


# =============================================================================
# HEARTBEAT — reroda a página quando um novo snapshot é publicado.
# Enquanto o warm está em execução, a versão NÃO muda e a página permanece
# exibindo os dados antigos (estática).
# =============================================================================
@st.fragment(run_every="15s")
def _keep_cache_warm():
    version_atual = get_active_cache_version()
    chave = "_cache_version_positivacao"
    anterior = st.session_state.get(chave)

    if anterior is None:
        st.session_state[chave] = version_atual
    elif version_atual != anterior:
        st.session_state[chave] = version_atual
        st.rerun()


def renderizar_pagina_positivacao():
    if st.button("🔄 Atualizar Dados"):
        # Dispara warm em thread separada — aquece uma chave nova e publica
        # atomicamente ao final. Nenhuma tela pisca.
        threading.Thread(
            target=trigger_warm,
            kwargs={"source": "manual"},
            daemon=True,
            name="CacheBackgroundRefresh-manual",
        ).start()
        st.toast("Aquecimento solicitado. Os gráficos atualizarão em instantes.", icon="🔥")

    cache_key = get_scoped_cache_key("positivacao")
    df = load_if_cache_ready(
        carregar_positivacao,
        "carregar_positivacao",
        cache_key,
    )
    if df is None:
        st.info("Os dados ainda não estão no cache. Aguarde o aquecimento ou clique em 'Atualizar Dados'.")
        return

    # Ativa o heartbeat (barato: só compara um inteiro a cada 15s).
    _keep_cache_warm()

    if df is not None and not df.empty:

        # --- 0. DERIVAÇÃO DAS COLUNAS DE TEMPO ---
        df = df.copy()
        df['Mes'] = df['Mes'].astype(int)
        df['Ano'] = df['Ano'].astype(int)
        df['Ordem_Tempo'] = df['Ano'] * 100 + df['Mes']
        meses_pt = {
            1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez',
        }
        df['Mes_Ano'] = (
            df['Mes'].map(meses_pt) + '/' + df['Ano'].astype(str).str[-2:]
        )

        # --- 1. ÁREA DE FILTROS ---
        if 'filtro_supervisor' not in st.session_state:
            st.session_state['filtro_supervisor'] = []

        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            supervisores = sorted(df['Supervisor'].unique())
            st.session_state['filtro_supervisor'] = [
                v for v in st.session_state['filtro_supervisor'] if v in supervisores
            ]
            filtro_sup = st.multiselect(
                "SUPERVISOR",
                supervisores,
                key='filtro_supervisor',
                placeholder="(Todos)",
            )
        with col2:
            setores = sorted(df['Setor'].unique())
            filtro_setor = st.multiselect("SETOR", setores, placeholder="(Todos)")
        with col3:
            industrias = sorted(df['Industria'].unique())
            filtro_ind = st.multiselect("INDUSTRIA", industrias, placeholder="(Todos)")
        with col4:
            vendedores = sorted(df['Vendedor'].unique())
            filtro_vend = st.multiselect("PROMOTOR DE VENDAS", vendedores, placeholder="(Todos)")
        with col5:
            cidades = sorted(df['Cidade'].unique())
            filtro_cidade = st.multiselect("CIDADE", cidades, placeholder="(Todos)")

        df_filtrado = df.copy()
        if filtro_sup:
            df_filtrado = df_filtrado[df_filtrado['Supervisor'].isin(filtro_sup)]
        if filtro_setor:
            df_filtrado = df_filtrado[df_filtrado['Setor'].isin(filtro_setor)]
        if filtro_ind:
            df_filtrado = df_filtrado[df_filtrado['Industria'].isin(filtro_ind)]
        if filtro_vend:
            df_filtrado = df_filtrado[df_filtrado['Vendedor'].isin(filtro_vend)]
        if filtro_cidade:
            df_filtrado = df_filtrado[df_filtrado['Cidade'].isin(filtro_cidade)]

        st.divider()

        # --- 2. PREPARAÇÃO DA TABELA PIVOT ---
        if not df_filtrado.empty:

            df_pivot = pd.pivot_table(
                df_filtrado,
                values='Venda',
                index=['Codigo', 'Cliente', 'Bandeira', 'Cidade', 'Setor'],
                columns='Mes_Ano',
                aggfunc='sum',
                fill_value=0
            ).reset_index()

            meses_ordenados = (
                df_filtrado[['Mes_Ano', 'Ordem_Tempo']]
                .drop_duplicates()
                .sort_values('Ordem_Tempo')['Mes_Ano']
                .tolist()
            )
            colunas_fixas = ['Codigo', 'Cliente', 'Bandeira', 'Cidade', 'Setor']

            colunas_existentes = [c for c in colunas_fixas if c in df_pivot.columns]
            meses_existentes = [m for m in meses_ordenados if m in df_pivot.columns]
            df_pivot = df_pivot[colunas_existentes + meses_existentes]

            # --- 3. CONFIGURAÇÃO VISUAL DA TABELA ---
            tabela_exibicao = df_pivot.copy()
            for mes in meses_existentes:
                tabela_exibicao[mes] = tabela_exibicao[mes].map(format_brl)

            c1, c2 = st.columns([3, 1])
            with c1:
                st.subheader("Clientes Positivados")
            with c2:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_pivot.to_excel(writer, index=False, sheet_name='Positivacao')

                st.download_button(
                    label="📥 Baixar Excel",
                    data=buffer.getvalue(),
                    file_name="relatorio_positivacao.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch"
                )

            st.dataframe(
                tabela_exibicao,
                width="stretch",
                hide_index=True,
                height=600,
                lazy=True,
                alt="Clientes positivados e respectivos indicadores nos filtros selecionados",
            )
            st.caption(f"Exibindo {len(df_pivot)} clientes positivados com base nos filtros.")

        else:
            st.info("Nenhuma venda encontrada para os filtros selecionados.")

    else:
        st.warning("Nenhum dado retornado ou ocorreu um erro na consulta.")


if __name__ == "__main__":
    renderizar_pagina_positivacao()