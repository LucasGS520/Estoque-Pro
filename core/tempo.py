"""Helpers centrais de data/hora do sistema.

Política de fuso horário: todo o sistema (gravação, comparação e exibição)
opera em hora local de Brasília (America/Sao_Paulo), como datetime naive —
compatível com as colunas DateTime do SQLite. O Brasil não adota mais
horário de verão, então não há ambiguidade de offset.

Nunca usar `datetime.utcnow()`, `datetime.now()` ou `date.today()` direto
no código da aplicação — sempre `tempo.agora()` / `tempo.hoje()`.
"""

import datetime
from zoneinfo import ZoneInfo

TZ_LOCAL = ZoneInfo("America/Sao_Paulo")


def agora() -> datetime.datetime:
    """Data e hora atuais em horário de Brasília, como datetime naive."""
    return datetime.datetime.now(TZ_LOCAL).replace(tzinfo=None)


def hoje() -> datetime.date:
    """Data atual em horário de Brasília."""
    return agora().date()
