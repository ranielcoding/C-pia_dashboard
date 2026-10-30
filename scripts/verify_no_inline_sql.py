#!/usr/bin/env python3
"""
verify_no_inline_sql.py — Scaneia queries/*.py e falla se encontrar SQL inline.

Uso:
    python scripts/verify_no_inline_sql.py

Saída:
    - Lista de arquivos com SQL inline (se encontrados)
    -.exit_code 1 se SQL inline for encontrado
    -exit_code 0 se nenhum SQL inline for encontrado
"""

import ast
import re
import sys
from pathlib import Path
from typing import List, Tuple


# Regex para detectar SQL em strings multilinha em Python
# Captura:
#   - f""" ... """  (f-string multilinha)
#   - """ ... """   (string multilinha simples)
#   - f''' ... '''  (f-string com aspas simples multilinha)
#   - ''' ... '''   (string com aspas simples multilinha)
SQL_IN_MULTILINE_PATTERN = re.compile(
    r'(?:f?"{3}|f\'{3}|"{3}|\'{3})',  # abertura de string multilinha (com ou sem f)
    re.DOTALL,
)

# Palavras-chave SQL que indicam que o conteúdo é SQL (não código Python)
SQL_KEYWORDS = re.compile(
    r'\b(SELECT|WITH|FROM|JOIN|WHERE|GROUP\s+BY|ORDER\s+BY|INSERT\s+INTO|UPDATE\s|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|UNION\s+ALL|CASE\s+WHEN|INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|OUTER\s+JOIN|ON\s+)\b',
    re.IGNORECASE,
)

# Pattern para detectar SQL dentro de strings de uma linha (ex: "SELECT * FROM..." ou f"...")
SINGLE_LINE_SQL_PATTERN = re.compile(
    r'(?:f?"|f?\x27")(.+?(?:SELECT|WITH|FROM|JOIN|WHERE|GROUP\s+BY|ORDER\s+BY|INSERT\s+INTO|UPDATE\s+DELETE\s+FROM).+?)(?:"|\x27{2})',
    re.IGNORECASE | re.DOTALL,
)


def extract_string_literals(file_path: Path) -> List[Tuple[int, str, str]]:
    """
    Extrai todas as string literals de um arquivo Python.
    Retorna lista de (linha, tipo, conteúdo).
    """
    content = file_path.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(file_path))
    results = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Obtém a linha aproximada (não é perfeita para strings multilinha, mas funciona)
            try:
                line_no = node.lineno
            except AttributeError:
                line_no = 1
            results.append((line_no, "simple", node.value))
        elif isinstance(node, ast.JoinedStr):
            # f-string
            try:
                line_no = node.lineno
            except AttributeError:
                line_no = 1
            # Para f-strings complexas, tentamos extrair o valor
            try:
                # ast.unparse pode ajudar, mas tem limitações
                results.append((line_no, "fstring", ast.unparse(node) if hasattr(ast, 'unparse') else str(node)))
            except Exception:
                results.append((line_no, "fstring", "[não extraível]"))

    return results


def has_sql_keywords(text: str) -> bool:
    """Verifica se o texto contém palavras-chave SQL."""
    return bool(SQL_KEYWORDS.search(text))


def scan_file_for_sql(file_path: Path) -> List[str]:
    """
    Scanne um arquivo Python em busca de SQL inline.
    Retorna lista de descrições das ocorrências encontradas.
    """
    findings = []
    content = file_path.read_text(encoding="utf-8")

    # 1. Verificar strings multilinha com SQL keywords
    multiline_matches = list(SQL_IN_MULTILINE_PATTERN.finditer(content))
    for match in multiline_matches:
        start_pos = match.start()
        # Pega o restante da string (próximo match ou fim do arquivo)
        next_matches = [m for m in multiline_matches if m.start() > start_pos]
        end_pos = next_matches[0].start() if next_matches else len(content)

        string_content = content[start_pos:end_pos]
        # Remove o delimitador
        string_content = re.sub(r'^f?".*?"|f\'.*\'', '', string_content, count=1, flags=re.DOTALL)
        string_content = re.sub(r'^".*?"|\'.*\'', '', string_content, count=1, flags=re.DOTALL)

        if has_sql_keywords(string_content):
            line_no = content[:start_pos].count('\n') + 1
            findings.append(
                f"  Linha ~{line_no}: string multilinha contém SQL keywords"
            )

    # 2. Verificar strings de uma linha com SQL
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        # Ignora comentários
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        # Procura por padrões de SQL em strings de uma linha
        if re.search(
            r'(?:f?".*?(?:SELECT|WITH|FROM|JOIN|WHERE).*?"|'
            r'f\'.*?(?:SELECT|WITH|FROM|JOIN|WHERE).*?\')',
            line,
            re.IGNORECASE,
        ):
            findings.append(f"  Linha {i}: string de uma linha contém SQL keywords")

    # 3. Verificar se a função retorna diretamente uma string SQL
    # (ex: return f"""...""")
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.Return):
            if isinstance(node.value, ast.JoinedStr):
                findings.append(f"  Linha {node.lineno}: return de f-string (possível SQL)")
            elif isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                if has_sql_keywords(node.value.value):
                    findings.append(f"  Linha {node.lineno}: return de string contendo SQL keywords")

    return findings


def main() -> int:
    project_root = Path(__file__).parent.parent
    queries_dir = project_root / "queries"

    if not queries_dir.exists():
        print(f"❌ Diretório {queries_dir} não encontrado.")
        return 1

    py_files = list(queries_dir.glob("*.py"))
    if not py_files:
        print(f"⚠️  Nenhum arquivo .py encontrado em {queries_dir}")
        return 0

    print(f"🔍 Verificando {len(py_files)} arquivos em {queries_dir}/")
    print("-" * 60)

    total_findings = 0
    flagged_files = []

    for py_file in sorted(py_files):
        findings = scan_file_for_sql(py_file)
        if findings:
            flagged_files.append(py_file.name)
            total_findings += len(findings)
            print(f"\n❌ {py_file.name}:")
            for finding in findings:
                print(finding)

    print("\n" + "-" * 60)
    if total_findings == 0:
        print("✅ NENHUM SQL inline encontrado em queries/*.py")
        print("   Todas as queries estão lendo do Query Vault (st.secrets).")
        return 0
    else:
        print(f"\n❌ ENCONTRADOS: {total_findings} ocorrência(ões) de SQL inline em {len(flagged_files)} arquivo(s)")
        print("\nArquivos flagados:")
        for name in flagged_files:
            print(f"  - {name}")
        print("\n🛑 CI deve ser interrompido. Remova o SQL inline dos arquivos acima.")
        print("   Mova as strings SQL para o secrets.toml e use query_vault.get_query_sql().")
        return 1


if __name__ == "__main__":
    sys.exit(main())
