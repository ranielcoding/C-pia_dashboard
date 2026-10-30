import streamlit as st
import streamlit_authenticator as stauth
from datetime import datetime

from app_config import load_app_config
from cache_loaders import get_dashboard_cache_snapshot
from access_rules import resolve_effective_access
from access_logging import log_page_access


# 1. CONFIGURAÇÃO INICIAL
st.set_page_config(page_title="Dashboard Divimed", layout="wide")

# Inicialização de estado (comum aos dois)
if "df_raw" not in st.session_state:
    st.session_state["df_raw"] = None

# --- AUTENTICAÇÃO ---
config = load_app_config()

if not config.get("credentials") or not config["credentials"].get("usernames"):
    st.error("Configuração de autenticação não encontrada. Defina DASHBOARD_CREDENTIALS_JSON ou mantenha o arquivo config.yaml com usuários válidos.")
    st.stop()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

authenticator.login(location='main')

# --- LÓGICA APÓS LOGIN ---
if st.session_state["authentication_status"]:
    
    # 2. CAPTURA O PERFIL DO USUÁRIO (com regras efetivas)
    username_logado = st.session_state["username"]

    try:
        effective_access = resolve_effective_access(config, username_logado)
    except ValueError as exc:
        st.error(f"Acesso negado: {exc}")
        st.stop()

    user_role = effective_access["role"]

    # Salva informações na sessão
    st.session_state["user_role"] = user_role
    st.session_state["effective_access"] = effective_access

    # Aplica filtros padrão de supervisor, se houver
    if effective_access.get("default_filters", {}).get("supervisor"):
        default_supervisor = effective_access["default_filters"]["supervisor"]
        st.session_state["default_supervisor_filter"] = default_supervisor
        st.session_state["sup"] = default_supervisor
        st.session_state["filtro_sup"] = default_supervisor
        st.session_state["filtro_supervisor"] = [default_supervisor]

    # 3. DEFINIÇÃO DAS PÁGINAS DISPONÍVEIS
    pg_home = st.Page("pages/page_home.py", title="Home", icon=":material/home:")
    pg_config = st.Page("pages/_cache_warm.py", title="Aquecer Caches", icon=":material/settings:")
    pg_venda = st.Page("pages/page_venda_geral.py", title="Venda Geral", icon=":material/bar_chart:")
    pg_painel = st.Page("pages/page_painel.py", title="Painel", icon=":material/business:")
    pg_financeiro = st.Page("pages/page_financeiro.py", title="A Pagar x A Receber", icon=":material/payments:")
    pg_estoque = st.Page("pages/page_estoque.py", title="Estoque", icon=":material/inventory_2:")
    pg_setores = st.Page("pages/page_setores.py", title="Setores", icon=":material/map:")
    pg_positivacao = st.Page("pages/page_positivacao.py", title="Positivação Geral", icon=":material/trending_up:")
    pg_comissao = st.Page("pages/page_comissao.py", title="Comissão", icon=":material/attach_money:")
    pg_comparativo = st.Page("pages/page_comparativo.py", title="Análise Comparativa", icon=":material/compare_arrows:")
    pg_acompanhamento = st.Page("pages/page_acompanhamento.py", title="Acompanhamento do Dia", icon=":material/work:")
    pg_analise_previsao = st.Page("pages/page_analise_previsao.py", title="Análise e Previsão", icon=":material/auto_awesome:")
    pg_pedidos = st.Page("pages/page_pedidos.py", title="Acompanhamento de Pedidos", icon=":material/assignment:")
    pg_equipamentos = st.Page("pages/page_gerenciar_equipamentos.py", title="Gerenciar Equipamentos", icon=":material/build:")

    # 4. FILTRO DE ACESSO POR PERFIL (mesclando listas, agora com análise e previsão)
    paginas_permitidas = []

    if user_role in ['admin', 'diretoria']:
        paginas_permitidas = [pg_acompanhamento, pg_pedidos, pg_venda, 
                              pg_painel, pg_positivacao, pg_comparativo, pg_setores,
                              pg_comissao, pg_financeiro, pg_estoque, 
                              pg_analise_previsao, pg_equipamentos, pg_config]
    elif user_role in ['gerente', 'inteligencia']:
        paginas_permitidas = [pg_acompanhamento, pg_pedidos, pg_venda, 
                              pg_painel, pg_positivacao, pg_comparativo, pg_setores,
                              pg_comissao, pg_estoque]
    elif user_role == 'supervisor':
        paginas_permitidas = [pg_acompanhamento, pg_pedidos, pg_venda, 
                              pg_painel, pg_positivacao, pg_comparativo, 
                              pg_setores, pg_comissao, pg_analise_previsao]
    elif user_role == 'televendas':
        paginas_permitidas = [pg_acompanhamento, pg_pedidos, pg_venda, 
                              pg_painel, pg_positivacao, pg_comparativo, pg_setores,
                              pg_comissao, pg_estoque]
    elif user_role in ['Parametrizacao']:
        paginas_permitidas = [pg_config]
    else:
        st.error("Seu usuário não possui um perfil de acesso válido.")
        st.stop()

    paginas_permitidas.insert(0, pg_home)
    st.session_state["allowed_page_titles"] = {
        page.title for page in paginas_permitidas
    }

    # 5. CONFIGURAÇÃO DA SIDEBAR E NAVEGAÇÃO
    with st.sidebar:
        st.markdown("### Dashboard Divimed")
        st.write(f"Usuário: **{st.session_state['name']}**")
        st.caption(f"Perfil: {user_role.capitalize()}")

        cache_snapshot = get_dashboard_cache_snapshot()
        st.caption(f"Snapshot: {cache_snapshot['snapshot_name']}")
        st.caption(f"Publicado em: {cache_snapshot['published_at']}")

        authenticator.logout('Sair', 'sidebar')
        st.divider()

    pg = st.navigation(paginas_permitidas)
    current_page_title = pg.title
    access_log_context = (username_logado, user_role, current_page_title)
    if st.session_state.get("access_log_context") != access_log_context:
        log_page_access(
            username=username_logado,
            role=user_role,
            page_title=current_page_title,
        )
        st.session_state["access_log_context"] = access_log_context
    pg.run()

elif st.session_state["authentication_status"] is False:
    st.error('Usuário ou senha incorretos')
elif st.session_state["authentication_status"] is None:
    st.info('Por favor, insira suas credenciais para acessar os relatórios.')