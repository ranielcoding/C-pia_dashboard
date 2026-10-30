import streamlit as st
import pandas as pd
import logging
import os
import threading
from contextvars import ContextVar
from datetime import datetime, timedelta
from pathlib import Path

from data_quality import prepare_dataframe
from queries import (
    pedidos_2_queries,
    experience_queries,
    comparativo_queries,
    pedidos_queries,
    setores_queries,
    positivacao_queries,
    estoque_queries,
    comissao_queries,
)

lazy from sqlalchemy import create_engine
from urllib.parse import quote_plus

_engine = None
_LOGGER = logging.getLogger(__name__)
_execution_source = ContextVar("cache_execution_source", default=None)



# TTL de 75 minutos (1h15) com agendador horário a cada 60min.
# Com o double-buffer versionado, a TTL serve apenas como rede de segurança
# caso o scheduler morra — o snapshot ativo nunca fica velho em operação normal.
CACHE_TTL = timedelta(minutes=75)


def get_dashboard_cache_snapshot():
    registry = _get_pointer_registry()
    with registry["lock"]:
        active_key = registry["active_key"]
        last_warm_at = registry["last_warm_at"]

    if last_warm_at:
        published_at = datetime.fromisoformat(last_warm_at).strftime("%d/%m/%Y %H:%M:%S")
        snapshot_name = active_key or "Snapshot sem identificador"
    else:
        published_at = "Aguardando publicação"
        snapshot_name = "Aguardando primeiro snapshot"

    return {
        "ttl_hours": 1,
        "cache_enabled": True,
        "refresh_mode": "background",
        "last_refresh": published_at,
        "source": "SQL Server via SQLAlchemy",
        "status": "ativo",
        "snapshot_name": snapshot_name,
        "published_at": published_at,
    }


def clear_dashboard_cache():
    global _engine
    cache_targets = [
        carregar_base_unica,
        painel_carregar_base_unica,
        carregar_base_comparativo,
        carregar_experience_mes,
        carregar_experience_dia,
        carregar_pedidos_do_dia,
        carregar_detalhamento_pedidos_do_dia,
        carregar_setores,
        carregar_positivacao,
        carregar_estoque,
        carregar_comissao,
        carregar_experience_page,
        carregar_experience_page_dia,
    ]
    for target in cache_targets:
        try:
            target.clear()
        except Exception:
            pass
    _get_cache_registry()["ready"].clear()
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass


@st.cache_resource(show_spinner=False)
def _get_cache_registry():
    return {"ready": set(), "lock": threading.Lock()}


@st.cache_resource(show_spinner=False)
def _get_pointer_registry():
    """
    Estado global do double-buffer de caches.

    - active_key : chave que TODAS as páginas devem ler (snapshot estável).
    - pending_key: chave sendo aquecida em background (não visível às páginas).
    - version    : incrementa apenas quando o snapshot é trocado com sucesso.
                   O st.fragment das páginas monitora este número.
    """
    return {
        "lock": threading.Lock(),
        "active_key": None,
        "pending_key": None,
        "version": 0,
        "last_warm_at": None,
    }


def is_cache_ready(loader_name, cache_key):
    registry = _get_cache_registry()
    with registry["lock"]:
        return (loader_name, cache_key) in registry["ready"]


def _mark_cache_ready(loader_name, cache_key):
    registry = _get_cache_registry()
    with registry["lock"]:
        registry["ready"].add((loader_name, cache_key))


def clear_loader_cache(loader, loader_name):
    loader.clear()
    registry = _get_cache_registry()
    with registry["lock"]:
        registry["ready"] = {
            item for item in registry["ready"] if item[0] != loader_name
        }


def load_if_cache_ready(loader, loader_name, cache_key, force=False, *args, **kwargs):
    if force or is_cache_ready(loader_name, cache_key):
        return loader(cache_key, *args, **kwargs)
    return None


def _load_sql_query(loader_name, cache_key, query_loader):
    _log_loader_start(loader_name, cache_key)
    try:
        with get_connection() as conn:
            df = query_loader(conn)
        _mark_cache_ready(loader_name, cache_key)
        return df
    except Exception:
        _LOGGER.exception("Erro na carga %s", loader_name)
        return None


def get_connection():
    global _engine
    db = st.secrets["database"]
    conn_str = (
        f"DRIVER={{{db['driver']}}};SERVER={db['server']};"
        f"DATABASE={db['database']};Trusted_Connection={db.get('trusted_connection','yes')};"
        f"TrustServerCertificate=yes;"
    )
    quoted = quote_plus(conn_str)
    if _engine is None:
        _engine = create_engine(
            f"mssql+pyodbc:///?odbc_connect={quoted}",
            connect_args={"timeout": 180},
            isolation_level="AUTOCOMMIT",
            pool_size=5,
            max_overflow=10,
            pool_recycle=1800,
            pool_pre_ping=True,
        )
    return _engine.connect()


def _get_execution_source():
    source = _execution_source.get()
    if source:
        return source
    thread_name = threading.current_thread().name
    if thread_name.startswith("CacheBackgroundRefresh"):
        return "background"
    if thread_name == "warm-scheduler":
        return "scheduler"
    return "page"


def _log_loader_start(loader_name, cache_key):
    _LOGGER.info(
        "Iniciando loader %s (origem=%s, cache_key=%s)",
        loader_name,
        _get_execution_source(),
        cache_key,
    )


# =============================================================================
# BASES PRINCIPAIS — TTL de 1h + refresh em background
# =============================================================================

@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_base_unica(cache_key):
    """Loader central mestre — usa comparativo_queries (superconjunto)."""
    _log_loader_start("carregar_base_unica", cache_key)
    try:
        agora = datetime.now()
        data_ini = datetime(agora.year - 1, 1, 1).strftime('%Y-%m-%d 00:00:00')
        data_fim = agora.strftime('%Y-%m-%d 23:59:59')
        sql = comparativo_queries.get_dados_agrupados(data_ini, data_fim)
        with get_connection() as conn:
            # Chunked read to avoid large contiguous allocation & memory fragmentation
            chunks = []
            chunk_size = 50000
            for chunk in pd.read_sql_query(sql, conn, chunksize=chunk_size):
                chunks.append(chunk)
            df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        if df.empty:
            _mark_cache_ready("carregar_base_unica", cache_key)
            return None
        df = prepare_dataframe(
            df,
            required_columns=['data', 'origem_venda', 'cod_digitador', 'Vendedor', 'SUPERVISOR'],
            numeric_columns=['valor_mercadoria', 'valor_venda', 'quantidade'],
            date_columns=['data'],
        )
        df['Ano'] = df['Ano'].fillna(0).astype(int)
        df['Mes'] = df['Mes'].fillna(0).astype(int)
        df['Equipe'] = df['origem_venda'].apply(lambda x: 'TELEVENDAS' if str(x).strip().lower() == 'televendas' else 'EXTERNA')
        df['Vendedor_Real'] = df['cod_digitador']
        df['Vendedor_Atribuido'] = df['Vendedor']
        df['Supervisor_Real'] = df['SUPERVISOR']
        _mark_cache_ready("carregar_base_unica", cache_key)
        return df
    except Exception:
        _LOGGER.exception("Erro na carga bruta")
        return None


@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def painel_carregar_base_unica(cache_key):
    """Delegate para carregar_base_unica — reutiliza o mesmo cache mestre."""
    _log_loader_start("painel_carregar_base_unica", cache_key)
    df = carregar_base_unica(cache_key)
    _mark_cache_ready("painel_carregar_base_unica", cache_key)
    return df


@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_base_comparativo(cache_key):
    """Delegate para carregar_base_unica — reutiliza o mesmo cache mestre."""
    _log_loader_start("carregar_base_comparativo", cache_key)
    df = carregar_base_unica(cache_key)
    _mark_cache_ready("carregar_base_comparativo", cache_key)
    return df


# =============================================================================
# EXPERIENCE — acumulado do mês + vendas do dia
# =============================================================================

@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_experience_mes(cache_key):
    """Acumulado do mês corrente por supervisor / vendedor / fornecedor."""
    _log_loader_start("carregar_experience_mes", cache_key)
    try:
        with get_connection() as conn:
            df = pedidos_2_queries.obter_dados_experience(conn)
        if df is None or df.empty:
            _mark_cache_ready("carregar_experience_mes", cache_key)
            return None
        _mark_cache_ready("carregar_experience_mes", cache_key)
        return df
    except Exception:
        _LOGGER.exception("Erro na carga do Experience (mês)")
        return None


@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_experience_dia(cache_key):
    """Vendas do dia atual por vendedor / fornecedor."""
    _log_loader_start("carregar_experience_dia", cache_key)
    try:
        with get_connection() as conn:
            df = pedidos_2_queries.obter_dados_vendas_dia(conn)
        if df is None or df.empty:
            _mark_cache_ready("carregar_experience_dia", cache_key)
            return None
        _mark_cache_ready("carregar_experience_dia", cache_key)
        return df
    except Exception:
        _LOGGER.exception("Erro na carga do Experience (dia)")
        return None


# =============================================================================
# PEDIDOS — listagem de pedidos do dia
# =============================================================================

@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_pedidos_do_dia(cache_key):
    """Pedidos digitados no dia atual (com todos os campos de detalhe)."""
    _log_loader_start("carregar_pedidos_do_dia", cache_key)
    try:
        with get_connection() as conn:
            df = pedidos_queries.obter_pedidos_do_dia(conn)
        if df is None or df.empty:
            _mark_cache_ready("carregar_pedidos_do_dia", cache_key)
            return None
        _mark_cache_ready("carregar_pedidos_do_dia", cache_key)
        return df
    except Exception:
        _LOGGER.exception("Erro na carga de pedidos do dia")
        return None


@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_detalhamento_pedidos_do_dia(cache_key):
    """Detalhamento por item dos pedidos do dia (usado no modal de detalhes)."""
    _log_loader_start("carregar_detalhamento_pedidos_do_dia", cache_key)
    try:
        with get_connection() as conn:
            df = pedidos_queries.obter_detalhamento_pedidos_do_dia(conn)
        if df is None or df.empty:
            _mark_cache_ready("carregar_detalhamento_pedidos_do_dia", cache_key)
            return None
        _mark_cache_ready("carregar_detalhamento_pedidos_do_dia", cache_key)
        return df
    except Exception:
        _LOGGER.exception("Erro na carga do detalhamento de pedidos do dia")
        return None


@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_setores(cache_key):
    return _load_sql_query(
        "carregar_setores", cache_key, setores_queries.obter_dados_setores
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_positivacao(cache_key):
    return _load_sql_query(
        "carregar_positivacao",
        cache_key,
        positivacao_queries.obter_dados_positivacao,
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_estoque(cache_key):
    return _load_sql_query(
        "carregar_estoque", cache_key, estoque_queries.obter_dados_estoque
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_comissao(cache_key, data_inicio, data_fim):
    return _load_sql_query(
        "carregar_comissao",
        cache_key,
        lambda conn: comissao_queries.obter_dados_comissao(
            conn, data_inicio, data_fim
        ),
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_experience_page(cache_key):
    return _load_sql_query(
        "carregar_experience_page",
        cache_key,
        experience_queries.obter_dados_experience,
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL, refresh_mode="background")
def carregar_experience_page_dia(cache_key):
    return _load_sql_query(
        "carregar_experience_page_dia",
        cache_key,
        experience_queries.obter_dados_vendas_dia,
    )


# =============================================================================
# CHAVES DE CACHE — double-buffering
# =============================================================================

def get_cache_key_diario():
    """Chave-BASE diária. Usada apenas para derivar chaves versionadas."""
    agora = datetime.now()
    if agora.hour < 4:
        base_date = agora - timedelta(days=1)
    else:
        base_date = agora
    return base_date.strftime("%Y-%m-%d_04:00")


def get_active_cache_key() -> str:
    """
    Chave que as PÁGINAS devem usar. Enquanto um warm está em execução,
    continua apontando para o snapshot antigo — gráficos ficam estáticos.
    Na primeira execução (bootstrap), assume a chave-base diária.
    """
    reg = _get_pointer_registry()
    with reg["lock"]:
        if reg["active_key"] is None:
            reg["active_key"] = get_cache_key_diario()
        return reg["active_key"]


def get_active_cache_version() -> int:
    """Incrementa apenas quando um warm é publicado com sucesso."""
    reg = _get_pointer_registry()
    with reg["lock"]:
        return reg["version"]


def get_scoped_cache_key(name: str) -> str:
    """Chave versionada para loaders auxiliares (setores, estoque, etc.)."""
    return f"{name}::{get_active_cache_key()}"


def _build_pending_key() -> str:
    """Gera uma chave NOVA por ciclo — força cache miss em todos os loaders."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{get_cache_key_diario()}::v{stamp}"


def _set_pending_key(key: str):
    reg = _get_pointer_registry()
    with reg["lock"]:
        reg["pending_key"] = key


def _publish_pending_key(final_key: str):
    """Troca atômica. Somente chamada quando o warm foi bem-sucedido."""
    reg = _get_pointer_registry()
    with reg["lock"]:
        reg["active_key"] = final_key
        reg["pending_key"] = None
        reg["version"] += 1
        reg["last_warm_at"] = datetime.now().isoformat(timespec="seconds")


def get_cache_key_comissao(data_inicio, data_fim):
    """Chave de comissão versionada com o snapshot ativo."""
    return (
        f"comissao:{data_inicio.isoformat()}:"
        f"{data_fim.isoformat()}::{get_active_cache_key()}"
    )


# =============================================================================
# WARM-UP (double-buffering: aquece chave nova e publica atomicamente)
# =============================================================================

def warm_all_caches():
    """
    Gerador que aquece um snapshot NOVO em background e, ao final, publica-o
    atomicamente. Enquanto isso, as páginas continuam servindo o snapshot
    antigo (active_key) — nenhuma quebra visual.
    Cada item é um dict: {step, start, end, duration, result, error}.
    O último item tem step='summary' (com 'published' e 'published_key').
    """
    start_total = datetime.now()
    source = _get_execution_source()
    log_messages = []

    def emit_step(step_name, start, end, result, error=None):
        record = {
            'step': step_name,
            'start': start.isoformat(timespec='seconds'),
            'end': end.isoformat(timespec='seconds'),
            'duration': (end - start).total_seconds(),
            'result': result,
            'error': error,
        }
        log_messages.append(record)
        return record

    hoje = datetime.now().date()
    inicio_mes = hoje.replace(day=1)

    # === CHAVE NOVA — obriga cache miss em TODOS os loaders ===
    new_key = _build_pending_key()
    _set_pending_key(new_key)

    def k(name: str) -> str:
        """Chave versionada para loaders auxiliares."""
        return f"{name}::{new_key}"

    comissao_key = (
        f"comissao:{inicio_mes.isoformat()}:{hoje.isoformat()}::{new_key}"
    )

    # ---------- 1. Cargas rápidas ----------
    fast_loads = [
        ("carregar_setores",             lambda: carregar_setores(k("setores"))),
        ("carregar_positivacao",         lambda: carregar_positivacao(k("positivacao"))),
        ("carregar_estoque",             lambda: carregar_estoque(k("estoque"))),
        ("carregar_comissao",            lambda: carregar_comissao(
            comissao_key, inicio_mes, hoje)),
        ("carregar_experience_page",     lambda: carregar_experience_page(k("experience_page"))),
        ("carregar_experience_page_dia", lambda: carregar_experience_page_dia(k("experience_page_dia"))),
    ]

    for step_name, load in fast_loads:
        t0 = datetime.now()
        try:
            ok = load() is not None
            yield emit_step(step_name, t0, datetime.now(), "OK" if ok else "vazia")
        except Exception as e:
            yield emit_step(step_name, t0, datetime.now(), None, str(e))

    # ---------- 2. Bases principais (todas com new_key) ----------
    principais = [
        ("carregar_base_unica",        lambda: carregar_base_unica(new_key)),
        ("painel_carregar_base_unica", lambda: painel_carregar_base_unica(new_key)),
        ("carregar_base_comparativo",  lambda: carregar_base_comparativo(new_key)),
        ("carregar_experience_mes",    lambda: carregar_experience_mes(new_key)),
        ("carregar_experience_dia",    lambda: carregar_experience_dia(new_key)),
        ("carregar_pedidos_do_dia",    lambda: carregar_pedidos_do_dia(new_key)),
        ("carregar_detalhamento_pedidos_do_dia",
            lambda: carregar_detalhamento_pedidos_do_dia(new_key)),
    ]

    for step_name, load in principais:
        t0 = datetime.now()
        try:
            ok = load() is not None
            yield emit_step(step_name, t0, datetime.now(), "OK" if ok else "vazia")
        except Exception as e:
            yield emit_step(step_name, t0, datetime.now(), None, str(e))

    # ---------- 3. Publicação atômica ----------
    # Só publica se TODOS os loaders críticos terminaram sem erro.
    # Se algum falhar, o snapshot antigo continua ativo (fail-safe).
    criticos = {
        "carregar_base_unica",
        "carregar_experience_mes",
        "carregar_experience_dia",
        "carregar_pedidos_do_dia",
    }
    falhas_criticas = [
        s for s in log_messages
        if s["step"] in criticos and (s.get("error") or s.get("result") not in ("OK", "vazia"))
    ]

    if falhas_criticas:
        _LOGGER.warning(
            "Warm concluído com falhas críticas — snapshot NÃO publicado. Falhas: %s",
            [s["step"] for s in falhas_criticas],
        )
        published = False
    else:
        _publish_pending_key(new_key)
        published = True

    total_dur = (datetime.now() - start_total).total_seconds()
    final_summary = {
        'total_duration': total_dur,
        'steps': log_messages,
        'source': source,
        'published': published,
        'published_key': new_key if published else None,
        'version': get_active_cache_version(),
    }
    yield {'step': 'summary', 'summary': final_summary}

    # Log em arquivo
    log_dir = Path("logs")
    try:
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"warm_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(
                f"{datetime.now().isoformat()} | source={source} | "
                f"published={published} | version={final_summary['version']} | "
                f"duration={total_dur:.2f}s\n"
            )
    except Exception:
        pass


# =============================================================================
# SCHEDULER SERVER-SIDE (roda independente de sessão/aba)
# =============================================================================

@st.cache_resource(show_spinner=False)
def _get_scheduler_state():
    """Estado global compartilhado entre todas as sessões do processo Streamlit."""
    return {
        "started": False,
        "thread": None,
        "stop_event": threading.Event(),
        "history": [],
        "next_run": None,
        "lock": threading.Lock(),
        "warm_lock": threading.Lock(),
        "warming": False,
        "warming_source": None,
        "warming_started_at": None,
    }


def _executar_warming(source="manual") -> dict:
    """Roda um warm exclusivo e devolve {timestamp, source, steps, summary}."""
    state = _get_scheduler_state()
    if not state["warm_lock"].acquire(blocking=False):
        with state["lock"]:
            current_source = state["warming_source"]
            started_at = state["warming_started_at"]
        return {
            "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "source": source,
            "status": "skipped",
            "reason": (
                f"Warm já em execução ({current_source}, iniciado em "
                f"{started_at})."
            ),
            "steps": [],
            "summary": {"total_duration": 0, "steps": []},
        }

    with state["lock"]:
        state["warming"] = True
        state["warming_source"] = source
        state["warming_started_at"] = datetime.now().strftime(
            "%d/%m/%Y %H:%M:%S"
        )

    agora = datetime.now()
    execucao = {
        "timestamp": agora.strftime("%d/%m/%Y %H:%M:%S"),
        "source": source,
        "status": "completed",
        "steps": [],
    }
    token = _execution_source.set(source)
    try:
        for update in warm_all_caches():
            if update.get("step") == "summary":
                execucao["summary"] = update["summary"]
                break
            execucao["steps"].append({
                "step": update["step"],
                "start": update.get("start"),
                "end": update.get("end"),
                "duration": update.get("duration", 0),
                "result": update.get("result"),
                "error": update.get("error"),
            })
        return execucao
    finally:
        _execution_source.reset(token)
        with state["lock"]:
            state["warming"] = False
            state["warming_source"] = None
            state["warming_started_at"] = None
        state["warm_lock"].release()


def _scheduler_loop(state: dict):
    """Acorda no topo de cada hora e executa o warm."""
    while not state["stop_event"].is_set():
        agora = datetime.now()
        proximo = agora.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        wait_seconds = max(1, (proximo - agora).total_seconds())

        with state["lock"]:
            state["next_run"] = proximo.strftime("%d/%m/%Y %H:%M:%S")

        if state["stop_event"].wait(timeout=wait_seconds):
            break

        try:
            execucao = _executar_warming(source="scheduler")
            if execucao["status"] == "completed":
                with state["lock"]:
                    state["history"].append(execucao)
                    if len(state["history"]) > 48:
                        state["history"] = state["history"][-48:]
        except Exception as e:
            print(f"[scheduler] Erro na execução agendada: {e}")


def start_hourly_scheduler():
    """Inicia o scheduler (idempotente). Pode ser chamado de qualquer sessão."""
    state = _get_scheduler_state()
    with state["lock"]:
        if state["thread"] and state["thread"].is_alive():
            return state
        state["stop_event"].clear()
        t = threading.Thread(
            target=_scheduler_loop,
            args=(state,),
            daemon=True,
            name="warm-scheduler",
        )
        state["thread"] = t
        state["started"] = True
        t.start()
    print("[scheduler] Scheduler horário iniciado.")
    return state


def stop_hourly_scheduler():
    state = _get_scheduler_state()
    with state["lock"]:
        thread = state["thread"]
        if not state["started"] and not (thread and thread.is_alive()):
            return
        state["stop_event"].set()
        state["started"] = False
    if thread and thread.is_alive() and thread is not threading.current_thread():
        thread.join()
    print("[scheduler] Scheduler horário parado.")


def get_scheduler_state():
    return _get_scheduler_state()


def is_scheduler_running() -> bool:
    state = _get_scheduler_state()
    with state["lock"]:
        return bool(state["started"] and state["thread"] and state["thread"].is_alive())


def is_warming_running() -> bool:
    state = _get_scheduler_state()
    with state["lock"]:
        return bool(state["warming"])


# =============================================================================
# API PÚBLICA DE WARM (para botões "Rodar agora" fora do _cache_warm.py)
# =============================================================================

def trigger_warm(source: str = "manual") -> dict:
    """Ponto público para disparar um warm sob demanda."""
    return _executar_warming(source=source)