import streamlit as st
import pandas as pd
import threading
import io
lazy import openpyxl
from cache_loaders import (
    carregar_estoque,
    get_scoped_cache_key,
    get_active_cache_version,
    load_if_cache_ready,
    trigger_warm,
)
from ui_theme import apply_dashboard_theme, page_header

apply_dashboard_theme()


# =============================================================================
# HEARTBEAT — reroda a página quando um novo snapshot é publicado.
# =============================================================================
@st.fragment(run_every="15s")
def _keep_cache_warm():
    version_atual = get_active_cache_version()
    chave = "_cache_version_estoque"
    anterior = st.session_state.get(chave)

    if anterior is None:
        st.session_state[chave] = version_atual
    elif version_atual != anterior:
        st.session_state[chave] = version_atual
        st.rerun()


def renderizar_pagina_estoque():
    page_header("📦 Visão Geral de Estoque", "Resumo dos produtos em estoque e seu giro.", icon="📦")

    if st.button("🔄 Atualizar Dados"):
        threading.Thread(
            target=trigger_warm,
            kwargs={"source": "manual"},
            daemon=True,
            name="CacheBackgroundRefresh-manual",
        ).start()
        st.toast("Aquecimento solicitado. A página atualizará em instantes.", icon="🔥")

    cache_key = get_scoped_cache_key("estoque")
    df_estoque = load_if_cache_ready(
        carregar_estoque,
        "carregar_estoque",
        cache_key,
    )
    if df_estoque is None:
        st.info("Os dados ainda não estão no cache. Aguarde o aquecimento ou clique em 'Atualizar Dados'.")
        return

    df_estoque = df_estoque.drop(
        columns=["Estoque Lote", "Lote", "Validade"],
        errors="ignore",
    ).drop_duplicates(subset=["Codigo Produto"], keep="first")

    # Ativa o heartbeat (barato: só compara um inteiro a cada 15s).
    _keep_cache_warm()

    if df_estoque is not None and not df_estoque.empty:

        col_esq, col_dir = st.columns([1, 3])

        with col_esq:
            st.subheader("Filtros por Fornecedor")
            produtos_selecionados = []
            fornecedores = sorted(df_estoque['Fornecedor'].dropna().unique())

            for fornecedor in fornecedores:
                with st.expander(fornecedor):
                    produtos_do_fornecedor = sorted(df_estoque[df_estoque['Fornecedor'] == fornecedor]['Descrição'].dropna().unique())

                    selecionar_todos = st.checkbox("Selecionar todos", key=f"all_{fornecedor}")

                    if selecionar_todos:
                        produtos_selecionados.extend(produtos_do_fornecedor)
                    else:
                        selecionados = st.multiselect(
                            "Produtos",
                            produtos_do_fornecedor,
                            key=f"multi_{fornecedor}",
                            label_visibility="collapsed",
                            placeholder="Escolha os produtos..."
                        )
                        produtos_selecionados.extend(selecionados)

        if produtos_selecionados:
            df_filtrado = df_estoque[df_estoque['Descrição'].isin(produtos_selecionados)]
        else:
            df_filtrado = df_estoque

        with col_dir:
            c1, c2 = st.columns([3, 1])
            with c1:
                st.subheader("Listagem de Produtos")

            with c2:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_filtrado.to_excel(writer, index=False, sheet_name='Estoque')

                st.download_button(
                    label="📥 Baixar Excel",
                    data=buffer.getvalue(),
                    file_name="relatorio_estoque.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch"
                )

            st.dataframe(
                df_filtrado,
                width="stretch",
                hide_index=True,
                height=650,
                lazy=True,
                alt="Estoque de produtos filtrado por fornecedor e produto",
            )

            st.caption(f"Exibindo {len(df_filtrado)} registros.")

    else:
        st.warning("Nenhum dado de estoque foi retornado ou ocorreu um erro na consulta.")


if __name__ == "__main__":
    renderizar_pagina_estoque()