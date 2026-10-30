import streamlit as st

from ui_theme import page_header

page_header(
    "Dashboard Divimed",
    "Um ponto de partida para acompanhar resultados, consultar operações "
    "e explorar os relatórios liberados para o seu perfil.",
    icon=":material/home:",
)

intro, data_info = st.columns([1.5, 1], gap="medium")
with intro:
    with st.container(border=True):
        st.subheader("Como começar", icon=":material/rocket_launch:")
        st.markdown(
            """
1. Abra um relatório pela navegação lateral.
2. Defina os filtros e confira o período e o escopo selecionados.
3. Analise os indicadores e detalhamentos apresentados.
4. Se necessário, use **Atualizar Dados** para solicitar uma atualização.
"""
        )

with data_info:
    with st.container(border=True):
        st.subheader("Dados e acesso", icon=":material/database:")
        st.write(
            "Os relatórios consultam snapshots publicados pelo processo de cache. "
            "Se os dados ainda não estiverem disponíveis, aguarde a publicação "
            "ou contate o administrador."
        )
        st.caption("As páginas disponíveis respeitam o perfil da sua conta.")

st.header("Guia das páginas", icon=":material/menu_book:")
allowed_page_titles = set(st.session_state.get("allowed_page_titles", {"Home"}))
page_guides = {
    "Painel": (
        "Painel e vendas",
        "Visão consolidada de faturamento, evolução diária, origem das vendas e "
        "rankings. Use filtros de supervisor, vendedor, televendas e período.",
        ":material/business:",
    ),
    "Venda Geral": (
        "Painel e vendas",
        "Analise indicadores, origem e evolução diária das vendas, produtos mais "
        "vendidos e detalhamento. Filtros de equipe e data ajustam o escopo.",
        ":material/bar_chart:",
    ),
    "Análise Comparativa": (
        "Painel e vendas",
        "Compare 2025 e 2026. Alterne entre valor de mercadoria, valor de venda "
        "por nota fiscal e quantidade.",
        ":material/compare_arrows:",
    ),
    "Positivação Geral": (
        "Clientes e operações",
        "Explore clientes positivados usando filtros de supervisor, setor, "
        "indústria, promotor de vendas e cidade.",
        ":material/trending_up:",
    ),
    "Acompanhamento do Dia": (
        "Clientes e operações",
        "Consulte acumulado mensal por supervisor e vendedor, valores do dia por "
        "origem e quantidade de pedidos. O filtro de fornecedor restringe os dados.",
        ":material/today:",
    ),
    "Acompanhamento de Pedidos": (
        "Clientes e operações",
        "Consulte pedidos e seus itens, quantidades pedidas, atendidas ou cortadas "
        "e motivos de falta. O detalhamento pode ser exportado.",
        ":material/assignment:",
    ),
    "Setores": (
        "Clientes e operações",
        "Consulte carteira e dados dos clientes por supervisor, vendedor, setor, "
        "cidade e bairro.",
        ":material/map:",
    ),
    "Estoque": (
        "Clientes e operações",
        "Consulte estoque total e filtre produtos por fornecedor. Lote e validade "
        "são reservados a análises específicas.",
        ":material/inventory_2:",
    ),
    "Análise e Previsão": (
        "Clientes e operações",
        "Analise previsão de fechamento mensal (P10, P50 e P90), tendência, risco "
        "de validade e perfis de clientes. Ajuste filtros e selecione a análise.",
        ":material/insights:",
    ),
    "A Pagar x A Receber": (
        "Financeiro e administração",
        "Analise títulos por período, situação e operação. Explore rankings e "
        "detalhamentos de vendas a receber ou compras a pagar.",
        ":material/payments:",
    ),
    "Comissão": (
        "Financeiro e administração",
        "Consulte comissões no período selecionado e refine pelos filtros de "
        "supervisor e promotor.",
        ":material/paid:",
    ),
    "Gerenciar Equipamentos": (
        "Financeiro e administração",
        "Cadastre, liste, edite ou exclua equipamentos. Confira o item antes de "
        "confirmar alterações ou exclusões.",
        ":material/computer:",
    ),
    "Aquecer Caches": (
        "Financeiro e administração",
        "Ferramenta administrativa para executar ou acompanhar o agendador de "
        "atualização dos dados. O acesso pode exigir uma chave.",
        ":material/cached:",
    ),
}
category_order = [
    "Painel e vendas",
    "Clientes e operações",
    "Financeiro e administração",
]
visible_guides = {
    title: guide
    for title, guide in page_guides.items()
    if title in allowed_page_titles
}
visible_categories = [
    category
    for category in category_order
    if any(guide[0] == category for guide in visible_guides.values())
]
if visible_categories:
    category_tabs = st.tabs(visible_categories)
    for category, tab in zip(visible_categories, category_tabs):
        with tab:
            entries = [
                (title, description, icon)
                for title, (page_category, description, icon) in visible_guides.items()
                if page_category == category
            ]
            for start in range(0, len(entries), 2):
                columns = st.columns(2, gap="medium")
                for column, (title, description, icon) in zip(
                    columns, entries[start : start + 2]
                ):
                    with column:
                        with st.container(border=True):
                            st.subheader(title, icon=icon)
                            st.write(description)
else:
    st.info(
        "Não há relatórios adicionais associados ao seu perfil. "
        "Consulte o administrador se precisar de acesso."
    )

with st.container(border=True):
    st.subheader("Boas práticas", icon=":material/lightbulb:")
    tips_left, tips_right = st.columns(2, gap="medium")
    with tips_left:
        st.markdown(
            """
- Confira filtros, período e escopo antes de comparar indicadores.
- Se não houver resultados, revise ou amplie os filtros selecionados.
"""
        )
    with tips_right:
        st.markdown(
            """
- Aguarde o snapshot quando uma página informar que os dados ainda não estão disponíveis.
- Respeite o escopo do seu perfil ao consultar ou compartilhar resultados.
"""
        )
