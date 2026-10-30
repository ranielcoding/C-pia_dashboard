import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from ui_theme import page_header

# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================
st.set_page_config(page_title="Gerenciamento de Equipamentos", layout="wide")
page_header("Gerenciamento de Equipamentos", icon=":material/computer:")

DB_PATH = "equipamentos.db"

# =========================================================
# LISTAS DE OPÇÕES
# =========================================================
SETORES = ["Administrativo/Fiscal/RH", "Financeiro", "TI", "Televendas", 
           "Conferência", "Reabastecimento", "SAC", "Marketing", "Entrada Mercadoria", 
           "Saída Mercadoria", "Faturamento", "Recepção", "Diretoria"]
EQUIPAMENTOS = ["SRV","Desktop", "Notebook", "All-in-One"]
VERSOES_WINDOWS = ["Windows 7", "Windows 8", "Windows 10", "Windows 11", "Windows Server", "Linux"]
IMPRESSORAS = ["Nenhuma", "HP LaserJet Pro M453-454 em 192.168.0.57", "HP LaserJet Pro 4003dw em 192.168.0.58", "HP LaserJet Pro M403-404 em 192.168.0.132", "Brother MFC-7860DW Printer em 192.168.0.2", "HP LaserJet Professional M1132 MFP em 192.168.0.77", "Outra"]

# Status com círculos coloridos
STATUS_OPCOES = [
    "🟢 OK",
    "🟡 Dá pra usar, mas pode ser trocado",
    "🔴 Precisa trocar",
]

# =========================================================
# BANCO DE DADOS
# =========================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS equipamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setor TEXT,
            nome_estacao TEXT,
            usuario TEXT,
            ip TEXT,
            equipamento TEXT,
            configuracao TEXT,
            versao_windows TEXT,
            numero_ramal TEXT,
            numero_chip TEXT,
            numero_whatsapp TEXT,
            email_outlook TEXT,
            email_gmail TEXT,
            mouse TEXT,
            teclado TEXT,
            monitor TEXT,
            caixa_som TEXT,
            fone_ouvido TEXT,
            fone_ramal TEXT,
            base_discadora TEXT,
            sistemas_utilizados TEXT,
            impressora_conectada TEXT,
            senhas_chrome TEXT,
            criado_em TEXT,
            atualizado_em TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect(DB_PATH)

def inserir(dados):
    conn = get_conn()
    c = conn.cursor()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO equipamentos (
            setor, nome_estacao, usuario, ip, equipamento, configuracao,
            versao_windows, numero_ramal, numero_chip, numero_whatsapp,
            email_outlook, email_gmail, mouse, teclado, monitor, caixa_som,
            fone_ouvido, fone_ramal, base_discadora, sistemas_utilizados,
            impressora_conectada, senhas_chrome, criado_em, atualizado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (*dados, agora, agora))
    conn.commit()
    conn.close()

def atualizar(id_reg, dados):
    conn = get_conn()
    c = conn.cursor()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        UPDATE equipamentos SET
            setor=?, nome_estacao=?, usuario=?, ip=?, equipamento=?, configuracao=?,
            versao_windows=?, numero_ramal=?, numero_chip=?, numero_whatsapp=?,
            email_outlook=?, email_gmail=?, mouse=?, teclado=?, monitor=?, caixa_som=?,
            fone_ouvido=?, fone_ramal=?, base_discadora=?, sistemas_utilizados=?,
            impressora_conectada=?, senhas_chrome=?, atualizado_em=?
        WHERE id=?
    """, (*dados, agora, id_reg))
    conn.commit()
    conn.close()

def deletar(id_reg):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM equipamentos WHERE id=?", (id_reg,))
    conn.commit()
    conn.close()

def listar_todos():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM equipamentos ORDER BY id DESC", conn)
    conn.close()
    return df

def buscar_por_id(id_reg):
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM equipamentos WHERE id=?", conn, params=(id_reg,))
    conn.close()
    return df.iloc[0] if not df.empty else None

# Inicializa banco
init_db()

# =========================================================
# FORMULÁRIO (usado em cadastro e edição)
# =========================================================
def formulario(dados=None, key_prefix="novo"):
    d = dados if dados is not None else {}

    with st.form(key=f"form_{key_prefix}"):

        st.markdown("### 📋 Informações Gerais")
        col1, col2, col3 = st.columns(3)
        with col1:
            setor = st.selectbox("SETOR", SETORES,
                                 index=SETORES.index(d.get("setor")) if d.get("setor") in SETORES else 0)
        with col2:
            nome_estacao = st.text_input("NOME DA ESTAÇÃO", value=d.get("nome_estacao", ""), required=True)
        with col3:
            usuario = st.text_input("USUÁRIO", value=d.get("usuario", ""), required=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            ip = st.text_input("IP", value=d.get("ip", ""), required=True)
        with col2:
            equipamento = st.selectbox("EQUIPAMENTO", EQUIPAMENTOS,
                                       index=EQUIPAMENTOS.index(d.get("equipamento")) if d.get("equipamento") in EQUIPAMENTOS else 0)
        with col3:
            versao_windows = st.selectbox("VERSÃO DO WINDOWS", VERSOES_WINDOWS,
                                          index=VERSOES_WINDOWS.index(d.get("versao_windows")) if d.get("versao_windows") in VERSOES_WINDOWS else 2)

        configuracao = st.text_area("CONFIGURAÇÃO", value=d.get("configuracao", ""), height=80)

        st.markdown("### ☎️ Contatos")
        col1, col2, col3 = st.columns(3)
        with col1:
            numero_ramal = st.text_input("NÚMERO RAMAL", value=d.get("numero_ramal", ""))
        with col2:
            numero_chip = st.text_input("NÚMERO CHIP", value=d.get("numero_chip", ""))
        with col3:
            numero_whatsapp = st.text_input("NÚMERO WHATSAPP", value=d.get("numero_whatsapp", ""))

        col1, col2 = st.columns(2)
        with col1:
            email_outlook = st.text_input(
                "EMAIL OUTLOOK",
                value=d.get("email_outlook", ""),
                type="email",
                validate=(r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$", "Informe um e-mail válido."),
            )
        with col2:
            email_gmail = st.text_input(
                "EMAIL GMAIL",
                value=d.get("email_gmail", ""),
                type="email",
                validate=(r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$", "Informe um e-mail válido."),
            )

        st.markdown("### 🖱️ Periféricos e Status")

        def status_select(label, valor_atual, key):
            idx = STATUS_OPCOES.index(valor_atual) if valor_atual in STATUS_OPCOES else 0
            return st.selectbox(label, STATUS_OPCOES, index=idx, key=key)

        col1, col2, col3 = st.columns(3)
        with col1:
            mouse = status_select("MOUSE", d.get("mouse"), f"{key_prefix}_mouse")
        with col2:
            teclado = status_select("TECLADO", d.get("teclado"), f"{key_prefix}_teclado")
        with col3:
            monitor = status_select("MONITOR", d.get("monitor"), f"{key_prefix}_monitor")

        col1, col2, col3 = st.columns(3)
        with col1:
            caixa_som = status_select("CAIXA DE SOM", d.get("caixa_som"), f"{key_prefix}_som")
        with col2:
            fone_ouvido = status_select("FONE DE OUVIDO", d.get("fone_ouvido"), f"{key_prefix}_fone")
        with col3:
            fone_ramal = status_select("FONE DE RAMAL", d.get("fone_ramal"), f"{key_prefix}_ramal")

        col1, col2 = st.columns(2)
        with col1:
            base_discadora = status_select("BASE DISCADORA", d.get("base_discadora"), f"{key_prefix}_base")
        with col2:
            impressora_conectada = st.selectbox(
                "IMPRESSORA CONECTADA", IMPRESSORAS,
                index=IMPRESSORAS.index(d.get("impressora_conectada")) if d.get("impressora_conectada") in IMPRESSORAS else 0
            )

        st.markdown("### ⚙️ Outros")
        sistemas_utilizados = st.text_area("SISTEMAS UTILIZADOS", value=d.get("sistemas_utilizados", ""), height=80)
        senhas_chrome = st.text_area("SENHAS DO CHROME", value=d.get("senhas_chrome", ""), height=80)

        submitted = st.form_submit_button(
            "Salvar", icon=":material/save:", width="stretch"
        )

    if submitted:
        dados_tupla = (
            setor, nome_estacao, usuario, ip, equipamento, configuracao,
            versao_windows, numero_ramal, numero_chip, numero_whatsapp,
            email_outlook, email_gmail, mouse, teclado, monitor, caixa_som,
            fone_ouvido, fone_ramal, base_discadora, sistemas_utilizados,
            impressora_conectada, senhas_chrome
        )
        return dados_tupla
    return None

# =========================================================
# INTERFACE PRINCIPAL - ABAS
# =========================================================
aba1, aba2, aba3, aba4 = st.tabs([
    ":material/add: Cadastrar",
    ":material/list: Listar",
    ":material/edit: Editar",
    ":material/delete: Excluir",
])

# -------- CADASTRAR --------
with aba1:
    st.subheader("Cadastrar Novo Equipamento")
    resultado = formulario(key_prefix="cad")
    if resultado:
        inserir(resultado)
        st.success("✅ Equipamento cadastrado com sucesso!")
        st.rerun()

# -------- LISTAR --------
with aba2:
    st.subheader("Equipamentos Cadastrados")
    df = listar_todos()

    if df.empty:
        st.info("Nenhum equipamento cadastrado ainda.")
    else:
        # Filtro por setor
        filtro_setor = st.multiselect("Filtrar por Setor", SETORES, default=SETORES)
        df_filtrado = df[df["setor"].isin(filtro_setor)] if filtro_setor else df

        st.caption(f"Total: **{len(df_filtrado)}** equipamento(s)")
        st.dataframe(
            df_filtrado,
            width="stretch",
            hide_index=True,
            lazy=True,
            alt="Equipamentos cadastrados, filtrados por setor",
        )

        # Exportar CSV
        csv = df_filtrado.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Baixar CSV", csv, "equipamentos.csv", "text/csv")

# -------- EDITAR --------
with aba3:
    st.subheader("Editar Equipamento")
    df = listar_todos()

    if df.empty:
        st.info("Nenhum equipamento cadastrado ainda.")
    else:
        opcoes = {f"ID {row['id']} - {row['nome_estacao']} ({row['usuario']})": row['id']
                  for _, row in df.iterrows()}
        escolha = st.selectbox("Selecione o equipamento para editar", list(opcoes.keys()))
        id_sel = opcoes[escolha]
        registro = buscar_por_id(id_sel)

        if registro is not None:
            resultado = formulario(registro.to_dict(), key_prefix=f"edit_{id_sel}")
            if resultado:
                atualizar(id_sel, resultado)
                st.success("✅ Equipamento atualizado com sucesso!")
                st.rerun()

# -------- EXCLUIR --------
with aba4:
    st.subheader("Excluir Equipamento")
    df = listar_todos()

    if df.empty:
        st.info("Nenhum equipamento cadastrado ainda.")
    else:
        opcoes = {f"ID {row['id']} - {row['nome_estacao']} ({row['usuario']})": row['id']
                  for _, row in df.iterrows()}
        escolha = st.selectbox("Selecione o equipamento para excluir", list(opcoes.keys()), key="del_sel")
        id_sel = opcoes[escolha]

        st.warning(f"⚠️ Você está prestes a excluir o equipamento **{escolha}**. Essa ação não pode ser desfeita.")

        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🗑️ Confirmar exclusão", type="primary"):
                deletar(id_sel)
                st.success("Equipamento excluído com sucesso!")
                st.rerun()