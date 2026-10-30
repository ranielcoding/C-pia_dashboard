from datetime import datetime

import streamlit as st
from ui_theme import page_header

from cache_loaders import (
    start_hourly_scheduler,
    stop_hourly_scheduler,
    get_scheduler_state,
    is_scheduler_running,
    is_warming_running,
    trigger_warm,
)

st.set_page_config(page_title="Warm Cache", layout="wide")
page_header("Aquecer Caches", icon=":material/cached:")

# ---------------------------------------------------------------------------
# Segredo
# ---------------------------------------------------------------------------
secret = None
try:
    secret = st.secrets["warm_key"]
except Exception:
    try:
        secret = st.secrets["general"]["warm_key"]
    except Exception:
        secret = None

if not secret:
    st.error("A secret 'warm_key' não está configurada em .streamlit/secrets.toml.")
    st.stop()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "warm_authorized" not in st.session_state:
    st.session_state.warm_authorized = False

st.caption(
    "Digite a chave uma vez. O agendador roda em background no servidor, "
    "independente de qualquer aba ou sessão, a cada hora cheia. "
    "Cada warm aquece uma versão NOVA em paralelo e publica atomicamente ao "
    "final — as páginas continuam exibindo o snapshot antigo até a troca."
)

# ---------------------------------------------------------------------------
# UI de autorização
# ---------------------------------------------------------------------------
if not st.session_state.warm_authorized:
    with st.form(key="warm_form"):
        warm_key_input = st.text_input(
            "Chave de aquecimento",
            type="password",
            key="warm_key_input",
        )
        submit = st.form_submit_button("Validar e iniciar agendador")

    if submit:
        if warm_key_input != secret:
            st.warning("Chave de aquecimento inválida. Verifique e tente novamente.")
        else:
            st.session_state.warm_authorized = True
            start_hourly_scheduler()
            st.success("✅ Chave validada. Agendador iniciado.")
            with st.spinner("Rodando warm inicial..."):
                execucao = trigger_warm(source="manual")
                state = get_scheduler_state()
                if execucao["status"] == "completed":
                    with state["lock"]:
                        state["history"].append(execucao)
            st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# Página autorizada
# ---------------------------------------------------------------------------
running = is_scheduler_running()
warming = is_warming_running()
if running:
    if warming:
        st.warning("🟡 Agendador ativo. Um warm está em execução.")
    else:
        st.success("🟢 Agendador ativo. Próximo warm no topo da próxima hora.")
else:
    state = get_scheduler_state()
    with state["lock"]:
        old_thread_alive = bool(state["thread"] and state["thread"].is_alive())
    if old_thread_alive:
        st.warning("🟡 Encerrando o scheduler anterior; aguarde o fim do warm.")
    else:
        st.warning("⚠️ Agendador parado. Reiniciando...")
        start_hourly_scheduler()

col_a, col_b = st.columns([1, 1])
with col_a:
    if st.button("▶️ Rodar agora", disabled=warming):
        execucao = trigger_warm(source="manual")
        state = get_scheduler_state()
        if execucao["status"] == "completed":
            with state["lock"]:
                state["history"].append(execucao)
            st.rerun()
        st.warning(execucao["reason"])
with col_b:
    if st.button("🛑 Parar agendador"):
        stop_hourly_scheduler()
        st.rerun()


# ---------------------------------------------------------------------------
# Painel de status — re-renderiza a cada 5s via fragment leve
# ---------------------------------------------------------------------------
@st.fragment(run_every="5s")
def _painel_status():
    state = get_scheduler_state()
    with state["lock"]:
        next_run = state["next_run"]
        history = list(reversed(state["history"]))
        running_now = state["started"] and state["thread"] and state["thread"].is_alive()
        warming_now = state["warming"]
        warming_source = state["warming_source"]

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Estado", "Ativo" if running_now else "Parado")
    with c2:
        st.metric("Próxima execução", next_run or "—")
    if warming_now:
        st.caption(f"Warm em execução — origem: `{warming_source}`")

    st.markdown("### 📜 Histórico de execuções")

    if not history:
        st.info("Nenhuma execução registrada ainda.")
        return

    for execucao in history:
        ts = execucao["timestamp"]
        source = execucao.get("source", "desconhecida")
        total = len(execucao["steps"])
        erros = sum(1 for s in execucao["steps"] if s.get("error"))
        icon = "🟢" if erros == 0 else "🔴"
        label = f"{icon}  [{ts}]  `{source}` —  {total - erros}/{total} OK"

        with st.expander(label, expanded=False):
            for step in execucao["steps"]:
                s_icon = "❌" if step.get("error") else "✅"
                dur = step.get("duration", 0)
                res = step.get("result") or step.get("error") or ""
                st.markdown(
                    f"&nbsp;&nbsp;&nbsp;&nbsp;{s_icon} **{step['step']}** "
                    f"— `{dur:.2f}s` — {res}"
                )
            summary = execucao.get("summary", {})
            if summary:
                st.caption(f"⏱ Duração total: {summary.get('total_duration', 0):.2f}s")
                if summary.get("published"):
                    st.caption(
                        f"🔑 Snapshot publicado: `{summary.get('published_key')}` "
                        f"(versão {summary.get('version')})"
                    )
                elif summary.get("published") is False:
                    st.caption("⚠️ Snapshot NÃO publicado (falhas críticas).")


_painel_status()