""" CLI de migracao avulsa.

Uso:
    python -m migration.migrate --estoque caminho/estoque.xlsx --fornecedores caminho/fornecedores.xlsx

As planilhas nao fazem parte da fonte principal do projeto. O SQLite em
data/estoque.db e a base operacional; este modulo serve apenas para importar
arquivos externos quando necessario.
"""

import argparse
import sys
from pathlib import Path

# Garante que o root do projeto esta no path ao rodar como modulo.
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_session_factory, init_db
from migration.loader import carregar_fornecedores, carregar_itens
from migration.parser import parse_estoque, parse_fornecedores
from migration.transformer import transformar_fornecedores, transformar_itens


def run(
    estoque_path: Path,
    fornecedores_path: Path,
) -> dict:
    """
    Executa a migração completa a partir de arquivos externos.

    Valida a existência das planilhas, inicializa o banco, executa parser,
    transformação e carga, e retorna um dict com resultados para exibição no
    Streamlit ou CLI. Pode lançar `FileNotFoundError` se algum arquivo não
    existir.
    """
    estoque_path = Path(estoque_path)
    fornecedores_path = Path(fornecedores_path)

    if not estoque_path.exists():
        raise FileNotFoundError(f"Planilha de estoque nao encontrada: {estoque_path}")
    if not fornecedores_path.exists():
        raise FileNotFoundError(f"Planilha de fornecedores nao encontrada: {fornecedores_path}")

    init_db()
    SessionLocal = get_session_factory()

    resultado: dict = {}

    print(f"[Estoque] Lendo: {estoque_path}")
    registros_brutos, erros_parser = parse_estoque(estoque_path)
    print(f"[Estoque] Registros brutos: {len(registros_brutos)}")

    itens, avisos = transformar_itens(registros_brutos)
    print(f"[Estoque] Itens apos normalizacao: {len(itens)} | Avisos: {len(avisos)}")
    if avisos:
        for aviso in avisos:
            print(f"  AVISO: {aviso}")

    with SessionLocal() as session:
        res_estoque = carregar_itens(session, itens, str(estoque_path.name), avisos + erros_parser)

    resultado["estoque"] = {
        "brutos": len(registros_brutos),
        "inseridos": res_estoque["ok"],
        "erros": res_estoque["erros"],
        "detalhes": res_estoque["detalhes"],
    }
    print(f"[Estoque] Inseridos: {res_estoque['ok']} | Erros: {res_estoque['erros']}")

    print(f"\n[Fornecedores] Lendo: {fornecedores_path}")
    forn_brutos, erros_forn_parser = parse_fornecedores(fornecedores_path)
    fornecedores = transformar_fornecedores(forn_brutos)
    print(f"[Fornecedores] Registros: {len(fornecedores)}")

    with SessionLocal() as session:
        res_forn = carregar_fornecedores(session, fornecedores, str(fornecedores_path.name))

    resultado["fornecedores"] = {
        "brutos": len(forn_brutos),
        "inseridos": res_forn["ok"],
        "erros": res_forn["erros"],
        "detalhes": res_forn["detalhes"] + erros_forn_parser,
    }
    print(f"[Fornecedores] Inseridos: {res_forn['ok']} | Erros: {res_forn['erros']}")
    print("\nMigracao concluida.")

    return resultado


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importa planilhas externas para o SQLite.")
    parser.add_argument("--estoque", required=True, type=Path, help="Caminho da planilha de estoque.")
    parser.add_argument("--fornecedores", required=True, type=Path, help="Caminho da planilha de fornecedores.")
    args = parser.parse_args()

    result = run(args.estoque, args.fornecedores)
    if result["estoque"]["erros"] > 0 or result["fornecedores"]["erros"] > 0:
        sys.exit(1)
