import streamlit as st
import pandas as pd
import threading
import io
from ui_theme import apply_dashboard_theme, page_header
from cache_loaders import (
    carregar_setores,
    get_scoped_cache_key,
    get_active_cache_version,
    load_if_cache_ready,
    trigger_warm,
)

apply_dashboard_theme()
page_header("🗺️ Visão Geral de Setores", "Resumo dos setores e suas características.", icon="🗺️")


# =============================================================================
# HEARTBEAT — reroda a página quando um novo snapshot é publicado.
# =============================================================================
@st.fragment(run_every="15s")
def _keep_cache_warm():
    version_atual = get_active_cache_version()
    chave = "_cache_version_setores"
    anterior = st.session_state.get(chave)

    if anterior is None:
        st.session_state[chave] = version_atual
    elif version_atual != anterior:
        st.session_state[chave] = version_atual
        st.rerun()


def renderizar_pagina_setores():
    if st.button("🔄 Atualizar Dados"):
        threading.Thread(
            target=trigger_warm,
            kwargs={"source": "manual"},
            daemon=True,
            name="CacheBackgroundRefresh-manual",
        ).start()
        st.toast("Aquecimento solicitado. A página atualizará em instantes.", icon="🔥")

    cache_key = get_scoped_cache_key("setores")
    df_setores = load_if_cache_ready(
        carregar_setores,
        "carregar_setores",
        cache_key,
    )
    if df_setores is None:
        st.info("Os dados ainda não estão no cache. Aguarde o aquecimento ou clique em 'Atualizar Dados'.")
        return

    # Ativa o heartbeat (barato: só compara um inteiro a cada 15s).
    _keep_cache_warm()

    if df_setores is not None and not df_setores.empty:

        st.subheader("Filtros")

        # --- Inicializa as seleções no session_state ---
        chaves_filtros = [
            'filtro_supervisor',
            'filtro_vendedor',
            'filtro_setor',
            'filtro_cidade',
            'filtro_bairro'
        ]
        for chave in chaves_filtros:
            if chave not in st.session_state:
                st.session_state[chave] = []

        mapa_colunas = {
            'filtro_supervisor': 'SUPERVISOR',
            'filtro_vendedor': 'Vendedor',
            'filtro_setor': 'Setor',
            'filtro_cidade': 'cidade',
            'filtro_bairro': 'bairro',
        }

        def aplicar_filtros_para_opcoes(df, excluir_chave=None):
            temp = df.copy()
            for chave, coluna in mapa_colunas.items():
                if chave == excluir_chave:
                    continue
                selecao = st.session_state.get(chave, [])
                if selecao:
                    temp = temp[temp[coluna].isin(selecao)]
            return temp

        opcoes_filtros = {}

        for chave in chaves_filtros:
            coluna = mapa_colunas[chave]
            df_opcoes = aplicar_filtros_para_opcoes(df_setores, excluir_chave=chave)
            opcoes = sorted(df_opcoes[coluna].dropna().unique())

            selecao_atual = st.session_state.get(chave, [])
            st.session_state[chave] = [v for v in selecao_atual if v in opcoes]

            opcoes_filtros[chave] = opcoes

        col_sup, col_vend, col_setor, col_cid, col_bairro = st.columns(5)

        with col_sup:
            filtro_supervisor = st.multiselect(
                "Supervisor",
                opcoes_filtros['filtro_supervisor'],
                key='filtro_supervisor',
                placeholder="Todos"
            )

        with col_vend:
            filtro_vendedor = st.multiselect(
                "Vendedor",
                opcoes_filtros['filtro_vendedor'],
                key='filtro_vendedor',
                placeholder="Todos"
            )

        with col_setor:
            filtro_setor = st.multiselect(
                "Setor",
                opcoes_filtros['filtro_setor'],
                key='filtro_setor',
                placeholder="Todos"
            )

        with col_cid:
            filtro_cidade = st.multiselect(
                "Cidade",
                opcoes_filtros['filtro_cidade'],
                key='filtro_cidade',
                placeholder="Todas"
            )

        with col_bairro:
            filtro_bairro = st.multiselect(
                "Bairro",
                opcoes_filtros['filtro_bairro'],
                key='filtro_bairro',
                placeholder="Todas"
            )

        df_filtrado = df_setores.copy()

        if filtro_supervisor:
            df_filtrado = df_filtrado[df_filtrado['SUPERVISOR'].isin(filtro_supervisor)]
        if filtro_vendedor:
            df_filtrado = df_filtrado[df_filtrado['Vendedor'].isin(filtro_vendedor)]
        if filtro_setor:
            df_filtrado = df_filtrado[df_filtrado['Setor'].isin(filtro_setor)]
        if filtro_cidade:
            df_filtrado = df_filtrado[df_filtrado['cidade'].isin(filtro_cidade)]
        if filtro_bairro:
            df_filtrado = df_filtrado[df_filtrado['bairro'].isin(filtro_bairro)]

        st.divider()

        c1, c2 = st.columns([4, 1])
        with c1:
            st.subheader("Listagem de Clientes")

        with c2:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_filtrado.to_excel(writer, index=False, sheet_name='Setores')

            st.download_button(
                label="📥 Baixar Excel",
                data=buffer.getvalue(),
                file_name="relatorio_setores.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch"
            )

        st.dataframe(
            df_filtrado,
            width="stretch",
            hide_index=True,
            height=600,
            lazy=True,
            alt="Clientes e vendas filtrados por setor, supervisor e região",
        )

        st.caption(f"Exibindo {len(df_filtrado)} registros.")

    else:
        st.warning("Nenhum dado de setores foi retornado ou ocorreu um erro na consulta.")


if __name__ == "__main__":
    renderizar_pagina_setores()