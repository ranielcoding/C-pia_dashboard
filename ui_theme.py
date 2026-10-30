from pathlib import Path

import streamlit as st

try:
    from streamlit.components.v2.component_manager import BidiComponentManager
    if not getattr(BidiComponentManager, "_ccv2_auto_discover_patched", False):
        _orig_bidi_init = BidiComponentManager.__init__

        def _patched_bidi_init(self, *args, **kwargs):
            _orig_bidi_init(self, *args, **kwargs)
            try:
                self.discover_and_register_components(start_file_watching=False)
            except Exception:
                pass

        BidiComponentManager.__init__ = _patched_bidi_init
        BidiComponentManager._ccv2_auto_discover_patched = True
except Exception:
    pass


def apply_dashboard_theme():
    """
    Aplica configurações de tema compatíveis com o Streamlit 1.66+.
    As cores principais, padding e sidebar são governados pelo .streamlit/config.toml.
    Mantido para retrocompatibilidade de importação das páginas.
    """
    pass


def page_header(title: str, subtitle: str = "", icon: str = ""):
    """Renderiza o logo e o título principal da página."""
    full_title = f"{icon} {title}".strip() if icon else title
    logo_path = Path(__file__).resolve().parent / "divimed_icon.jpg"
    logo_column, title_column = st.columns([0.12, 0.88], vertical_alignment="center")
    with logo_column:
        st.image(
            str(logo_path),
            width=76,
            alt="Logo da Divimed",
        )
    with title_column:
        st.header(full_title)
    if subtitle:
        st.caption(subtitle)
