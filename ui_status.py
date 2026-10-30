from datetime import datetime
import streamlit as st

from data_quality import summarize_data_quality


def status_card(title: str, value: str, tone: str = "info"):
    icon_map = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "danger": "🚨",
    }
    icon = icon_map.get(tone, "ℹ️")
    with st.container(border=True):
        st.caption(title)
        st.markdown(f"**{icon} {value}**")


def show_data_status(df, source_label="Dados", cache_state="cache ativo", required_columns=None):
    quality = summarize_data_quality(df, required_columns=required_columns)
    if quality["status"] == "healthy":
        status_card("Status da base", "Dados carregados com sucesso", "success")
        st.caption(
            f"Fonte: {source_label} | Cache: {cache_state} | Registros: {quality['rows']:,} | "
            f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        return True

    status_card("Status da base", "Atenção na base de dados", "warning")
    st.warning(quality["message"])
    if quality.get("missing_columns"):
        st.caption(f"Colunas ausentes: {quality['missing_columns']}")
    if quality.get("missing_values"):
        st.caption(f"Valores ausentes: {quality['missing_values']}")
    st.caption(
        f"Fonte: {source_label} | Cache: {cache_state} | Registros: {quality['rows']:,} | "
        f"Última verificação: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    return False


def show_alert_if_invalid(df, required_columns=None):
    quality = summarize_data_quality(df, required_columns=required_columns)
    if quality["status"] == "warning":
        st.warning(quality["message"])
        if quality.get("missing_columns"):
            st.caption(f"Colunas ausentes: {quality['missing_columns']}")
        return False

    return True
