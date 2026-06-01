"""
Normaliza os dados brutos do parser para objetos prontos para inserção no banco.
"""

import unicodedata


def normalizar_texto(texto: str) -> str:
    """Converte para ASCII lowercase sem acentos, para uso como chave de matching."""
    nfkd = unicodedata.normalize("NFKD", texto)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_str.lower().split())


def transformar_itens(registros: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Recebe registros brutos do parser e devolve:
    - lista de itens normalizados prontos para o loader
    - lista de avisos (duplicatas, etc.)

    Cada item de saída:
    {
        "categoria": str,
        "nome": str,
        "nome_normalizado": str,
        "estoque_atual": int,
        "estoque_minimo": int,   # sempre 0 — usuário preenche depois
        "estoque_ideal": int,    # sempre 0 — usuário preenche depois
        "unidade": str,
    }
    """
    avisos: list[str] = []
    itens: list[dict] = []

    # Detectar duplicatas por (categoria, nome_normalizado)
    vistos: dict[tuple, int] = {}

    for reg in registros:
        nome = reg["nome"].strip()
        if not nome:
            continue

        categoria = reg["categoria"].strip()
        nome_norm = normalizar_texto(nome)
        chave = (categoria, nome_norm)

        if chave in vistos:
            vistos[chave] += 1
            avisos.append(
                f"Duplicata detectada: '{nome}' em '{categoria}' "
                f"(ocorrência {vistos[chave]}). Mantendo a primeira entrada."
            )
            continue

        vistos[chave] = 1
        itens.append({
            "categoria": categoria,
            "nome": nome,
            "nome_normalizado": nome_norm,
            "estoque_atual": max(reg.get("estoque_atual") or 0, 0),
            "estoque_minimo": 0,
            "estoque_ideal": 0,
            "unidade": "un",
        })

    return itens, avisos


def transformar_fornecedores(registros: list[dict]) -> list[dict]:
    """Limpa e normaliza dados de fornecedores."""
    return [
        {
            "nome": r["nome"].strip(),
            "contato_nome": r.get("contato_nome"),
            "telefone": r.get("telefone"),
        }
        for r in registros
        if r.get("nome")
    ]
