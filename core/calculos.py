"""Motor stateless de cálculo automático de estoque mínimo e ideal.

Recebe listas de movimentações e retorna sugestões baseadas em
janela móvel de até 3 meses fechados, usando medianas e percentis para
evitar distorções por meses atípicos.

Quando o item tem menos de 3 meses de histórico, a janela se adapta
ao intervalo disponível (desde a primeira movimentação) e o resultado
é marcado como "historico_recente".

Sem dependências de banco de dados ou Streamlit — testável diretamente.
"""

import math
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass
class ResultadoRevisao:
    minimo_sugerido: Optional[int]
    ideal_sugerido: Optional[int]
    consumo_mediana_diario: Optional[float]
    consumo_p75_diario: Optional[float]
    intervalo_mediano_dias: Optional[int]
    intervalo_p90_dias: Optional[int]
    # ok / historico_insuficiente / historico_recente /
    # sem_consumo_recente / sem_entradas_recentes / irregular
    status_confiabilidade: str
    # Início real da janela usada (pode ser < 3 meses para itens novos)
    data_inicio_efetiva: Optional[date]


def calcular_janela(data_ref: date) -> tuple[date, date]:
    """Retorna o intervalo dos últimos 3 meses fechados a partir de data_ref.

    Ex: data_ref = 2026-06-01  →  (2026-03-01, 2026-05-31)
    """
    fim_mes = data_ref.replace(day=1) - timedelta(days=1)   # último dia do mês anterior
    inicio = fim_mes.replace(day=1) - timedelta(days=1)      # recua mais um mês
    inicio = inicio.replace(day=1) - timedelta(days=1)       # recua mais um mês
    inicio = inicio.replace(day=1)                           # primeiro dia, 3 meses atrás
    return inicio, fim_mes


def _percentil(valores: list[float], p: float) -> float:
    """Percentil via interpolação linear (equivalente a numpy percentile)."""
    if not valores:
        return 0.0
    s = sorted(valores)
    n = len(s)
    if n == 1:
        return s[0]
    idx = p / 100 * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return s[-1]
    frac = idx - lo
    return s[lo] + frac * (s[hi] - s[lo])


def _consumo_por_mes(
    saidas: list[tuple[date, int]],
    inicio: date,
    fim: date,
) -> list[float]:
    """Agrega saídas por mês natural e retorna consumo diário de cada mês.

    Para meses parciais (quando inicio/fim cortam o mês no meio), usa apenas
    os dias do mês que estão dentro da janela como denominador — isso evita
    subestimar o consumo diário de itens com histórico curto.
    """
    totais: dict[tuple[int, int], int] = defaultdict(int)
    for d, qtd in saidas:
        if inicio <= d <= fim:
            totais[(d.year, d.month)] += qtd

    consumos_diarios = []
    for (ano, mes), total in totais.items():
        # Dias efetivos dentro da janela para esse mês (lida com meses parciais)
        primeiro_do_mes = date(ano, mes, 1)
        ultimo_do_mes = date(ano, mes, monthrange(ano, mes)[1])
        inicio_efetivo_mes = max(primeiro_do_mes, inicio)
        fim_efetivo_mes = min(ultimo_do_mes, fim)
        dias_efetivos = (fim_efetivo_mes - inicio_efetivo_mes).days + 1
        if dias_efetivos > 0:
            consumos_diarios.append(total / dias_efetivos)
    return consumos_diarios


def _intervalos_entradas(entradas: list[tuple[date, int]]) -> list[int]:
    """Calcula os intervalos em dias entre entradas consecutivas."""
    datas = sorted(d for d, _ in entradas)
    return [(datas[i + 1] - datas[i]).days for i in range(len(datas) - 1)]


def _avaliar_confiabilidade(
    saidas: list[tuple[date, int]],
    entradas: list[tuple[date, int]],
    consumos_diarios: list[float],
    janela_curta: bool = False,
) -> str:
    """Determina o nível de confiabilidade do cálculo.

    janela_curta=True indica que o item tem menos de 3 meses de histórico;
    nesse caso o status é forçado para "historico_recente" (desde que haja
    algum dado — se não houver nada, retorna "historico_insuficiente").
    """
    if not saidas and not entradas:
        return "historico_insuficiente"

    # Se a janela já é curta, não precisamos investigar mais: é historico_recente
    if janela_curta:
        return "historico_recente"

    meses_com_saida = len(consumos_diarios)

    if meses_com_saida == 0 and entradas:
        return "sem_consumo_recente"

    if meses_com_saida > 0 and not entradas:
        return "sem_entradas_recentes"

    if meses_com_saida < 2:
        return "historico_recente"

    if meses_com_saida >= 2 and consumos_diarios:
        mediana = _percentil(consumos_diarios, 50)
        p75 = _percentil(consumos_diarios, 75)
        if mediana > 0 and p75 > 3 * mediana:
            return "irregular"

    return "ok"


def calcular_revisao_item(
    saidas: list[tuple[date, int]],
    entradas: list[tuple[date, int]],
    data_ref: date,
    data_primeira_mov: Optional[date] = None,
) -> ResultadoRevisao:
    """Calcula sugestões de estoque mínimo e ideal para um item.

    Args:
        saidas: lista de (data, quantidade) para movimentações do tipo "saida"
        entradas: lista de (data, quantidade) para movimentações do tipo "entrada"
        data_ref: data de referência (normalmente 1º do mês corrente)
        data_primeira_mov: data da primeira movimentação do item (qualquer tipo).
            Quando fornecida e posterior ao início da janela padrão, a janela é
            encurtada para cobrir apenas o histórico disponível.

    Returns:
        ResultadoRevisao com valores sugeridos, métricas intermediárias,
        status de confiabilidade e o início efetivo da janela usada.
    """
    inicio_padrao, fim = calcular_janela(data_ref)

    # Determina o início efetivo: usa primeira movimentação se mais recente que
    # o início dos 3 meses padrão, indicando que o item tem histórico curto.
    if data_primeira_mov is not None and data_primeira_mov > inicio_padrao:
        inicio_efetivo = data_primeira_mov
        janela_curta = True
    else:
        inicio_efetivo = inicio_padrao
        janela_curta = False

    saidas_janela = [(d, q) for d, q in saidas if inicio_efetivo <= d <= fim]
    entradas_janela = [(d, q) for d, q in entradas if inicio_efetivo <= d <= fim]

    consumos_diarios = _consumo_por_mes(saidas_janela, inicio_efetivo, fim)
    confiabilidade = _avaliar_confiabilidade(
        saidas_janela, entradas_janela, consumos_diarios, janela_curta=janela_curta
    )

    _sem_dados = ResultadoRevisao(
        minimo_sugerido=None, ideal_sugerido=None,
        consumo_mediana_diario=None, consumo_p75_diario=None,
        intervalo_mediano_dias=None, intervalo_p90_dias=None,
        status_confiabilidade=confiabilidade,
        data_inicio_efetiva=inicio_efetivo if janela_curta else None,
    )

    if confiabilidade == "historico_insuficiente":
        return _sem_dados

    # Métricas de consumo
    consumo_mediana = _percentil(consumos_diarios, 50) if consumos_diarios else None
    consumo_p75 = _percentil(consumos_diarios, 75) if consumos_diarios else None

    # Métricas de reposição
    intervalo_mediano = None
    intervalo_p90 = None
    if len(entradas_janela) >= 2:
        intervalos = _intervalos_entradas(entradas_janela)
        if intervalos:
            intervalo_mediano = math.ceil(_percentil(intervalos, 50))
            intervalo_p90 = math.ceil(_percentil(intervalos, 90))

    # Cálculo de mínimo e ideal só é possível com ambas as métricas
    if consumo_p75 is None or intervalo_mediano is None:
        return ResultadoRevisao(
            minimo_sugerido=None, ideal_sugerido=None,
            consumo_mediana_diario=consumo_mediana,
            consumo_p75_diario=consumo_p75,
            intervalo_mediano_dias=intervalo_mediano,
            intervalo_p90_dias=intervalo_p90,
            status_confiabilidade=confiabilidade,
            data_inicio_efetiva=inicio_efetivo if janela_curta else None,
        )

    minimo_sugerido = math.ceil(consumo_p75 * intervalo_mediano)

    consumo_esperado = (consumo_mediana or 0) * intervalo_mediano
    ideal_sugerido = math.ceil(minimo_sugerido + consumo_esperado)

    # Regra: ideal >= minimo + consumo_tipico_do_ciclo
    # saida_tipica_mensal é escalada para a duração real do ciclo de reposição,
    # evitando que itens com reposição frequente (< 30 dias) fiquem com ideal
    # inflado por uma comparação em escala mensal.
    if saidas_janela:
        totais_mes: dict[tuple[int, int], int] = defaultdict(int)
        for d, q in saidas_janela:
            totais_mes[(d.year, d.month)] += q
        saida_tipica_mensal = _percentil(list(totais_mes.values()), 50)
        saida_tipica_ciclo = math.ceil(saida_tipica_mensal * intervalo_mediano / 30.44)
        if ideal_sugerido < minimo_sugerido + saida_tipica_ciclo:
            ideal_sugerido = minimo_sugerido + saida_tipica_ciclo

    return ResultadoRevisao(
        minimo_sugerido=minimo_sugerido,
        ideal_sugerido=ideal_sugerido,
        consumo_mediana_diario=consumo_mediana,
        consumo_p75_diario=consumo_p75,
        intervalo_mediano_dias=intervalo_mediano,
        intervalo_p90_dias=intervalo_p90,
        status_confiabilidade=confiabilidade,
        data_inicio_efetiva=inicio_efetivo if janela_curta else None,
    )
