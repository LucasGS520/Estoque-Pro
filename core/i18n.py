"""Constantes de internacionalização compartilhadas pelo sistema."""

MESES_PT: dict[int, str] = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",    6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

# Lista com índice 1-based: índice 0 é string vazia para alinhar com month (1-12).
MESES_PT_LISTA: list[str] = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

# Abreviações com chave string "01"–"12" (usadas em formatação de eixo de gráficos).
MESES_ABREV: dict[str, str] = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}
