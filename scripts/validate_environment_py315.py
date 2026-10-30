# scripts/validate_environment_py315.py
"""
Script de auditoria de ambiente e compatibilidade com Python 3.15.
Garante que todo teste e verificação seja puramente virtual e local,
nunca tocando no diretório de produção.
"""

import sys
import platform
import argparse
import subprocess
import tempfile
from pathlib import Path

# Garantia de isolamento estrito
PROD_PATH = Path(r"C:\Users\raniel.veiga\Desktop\DASHBOARD")
WORKSPACE_PATH = Path.cwd().resolve()
REQUIREMENTS_PATH = Path(__file__).resolve().parent.parent / "requirements.txt"


def check_isolation() -> bool:
    print("=" * 60)
    print("1. VERIFICAÇÃO DE ISOLAMENTO DE PRODUÇÃO")
    print("=" * 60)
    print(f"Diretório atual de trabalho: {WORKSPACE_PATH}")
    print(f"Diretório de produção:       {PROD_PATH}")

    try:
        WORKSPACE_PATH.relative_to(PROD_PATH)
        is_inside_production = True
    except ValueError:
        is_inside_production = False

    if is_inside_production:
        print("[ALERTA CRÍTICO] O script está rodando no diretório de produção!")
        return False

    print("[OK] Executando em ambiente de cópia/desenvolvimento seguro.")
    return True


def audit_dependencies() -> dict:
    print("\n" + "=" * 60)
    print("2. INVENTÁRIO DE DEPENDÊNCIAS INSTALADAS")
    print("=" * 60)
    py_ver = sys.version_info
    print(f"Versão ativa do Python: {py_ver.major}.{py_ver.minor}.{py_ver.micro} ({platform.platform()})")

    packages_to_check = [
        ("streamlit", "Core do dashboard"),
        ("pandas", "Processamento tabular"),
        ("numpy", "Cálculos matemáticos e matrizes"),
        ("scipy", "Cálculos científicos e estatísticos"),
        ("scikit_learn", "Modelos de Machine Learning"),
        ("pyodbc", "Conexão com SQL Server (requer wheel para C-extension)"),
        ("plotly", "Gráficos interativos (Pure Python/JS)"),
        ("holidays", "Calendário e feriados (Pure Python)"),
        ("yaml", "Parser de configurações (PyYAML)"),
        ("sqlalchemy", "ORM e conexão pooling"),
    ]

    results = {}
    for pkg_name, description in packages_to_check:
        try:
            # Tratamento de nomes importáveis
            import_name = "sklearn" if pkg_name == "scikit_learn" else pkg_name
            mod = __import__(import_name)
            ver = getattr(mod, "__version__", "instalado")
            print(f"  [INSTALADO] {pkg_name:<15} v{ver:<10} - {description}")
            results[pkg_name] = {"status": "ok", "version": ver}
        except ImportError:
            print(f"  [AUSENTE]   {pkg_name:<15} - {description}")
            results[pkg_name] = {"status": "missing", "version": None}

    return results


def check_python_315_features():
    print("\n" + "=" * 60)
    print("3. VERIFICAÇÃO DE RECURSOS DO PYTHON 3.15")
    print("=" * 60)
    if sys.version_info >= (3, 15):
        print("[ATIVO] Interpretador Python 3.15 detectado.")
    else:
        print(f"[COMPATIBILIDADE] Interpretador Python {sys.version_info.major}.{sys.version_info.minor} ativo.")
        print("  - A compatibilidade de execução com Python 3.15 não foi testada neste interpretador.")


def configure_utf8_output():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def check_wheel_availability(target_python="3.15", target_platform="win_amd64"):
    """Checks wheel availability without installing packages or changing environments."""
    if not REQUIREMENTS_PATH.exists():
        raise FileNotFoundError(f"Arquivo de dependências não encontrado: {REQUIREMENTS_PATH}")

    requirements = [
        line.strip()
        for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-"))
    ]
    with tempfile.TemporaryDirectory(prefix="dashboard-py315-wheel-audit-") as temp_dir:
        command = [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--only-binary=:all:",
            "--implementation",
            "cp",
            "--python-version",
            target_python,
            "--abi",
            f"cp{target_python.replace('.', '')}",
            "--platform",
            target_platform,
            "--dest",
            temp_dir,
            *requirements,
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired:
            results = {
                "dependency tree": (
                    "timeout",
                    "Consulta da árvore completa de dependências excedeu 300 segundos.",
                )
            }
        else:
            downloaded = sorted(path.name for path in Path(temp_dir).glob("*.whl"))
            output = (result.stderr or result.stdout).strip().splitlines()
            if result.returncode == 0 and downloaded:
                results = {"dependency tree": ("ok", ", ".join(downloaded))}
            elif result.returncode == 0:
                results = {"dependency tree": ("error", "pip não baixou nenhum wheel compatível.")}
            else:
                detail = "\n".join(output[-8:]) or f"pip encerrou com código {result.returncode}."
                status = "unavailable" if "no matching distribution" in detail.lower() else "error"
                results = {"dependency tree": (status, detail)}

    print("\n" + "=" * 60)
    print(f"4. WHEELS PARA PYTHON {target_python} / {target_platform}")
    print("=" * 60)
    for requirement, (status, detail) in results.items():
        label = "WHEEL" if status == "ok" else status.upper()
        print(f"  [{label}] {requirement}: {detail}")

    return results


if __name__ == "__main__":
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Audita o ambiente local e wheels do Python 3.15.")
    parser.add_argument(
        "--check-wheels",
        action="store_true",
        help="Consulta o índice de pacotes por wheels do Python 3.15 sem instalar dependências.",
    )
    parser.add_argument(
        "--target-platform",
        default="win_amd64",
        help="Plataforma alvo para a consulta de wheels (padrão: win_amd64).",
    )
    args = parser.parse_args()

    if not check_isolation():
        sys.exit(2)

    audit_dependencies()
    check_python_315_features()
    print("\n[SUCESSO] Inventário do ambiente local concluído.")
    if args.check_wheels:
        wheel_results = check_wheel_availability(target_platform=args.target_platform)
        if any(status != "ok" for status, _ in wheel_results.values()):
            sys.exit(1)
        print("[SUCESSO] Todos os requisitos possuem wheel compatível com o alvo.")
