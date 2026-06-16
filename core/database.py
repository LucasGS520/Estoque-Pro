""" Configuração de banco de dados e sessões SQLAlchemy.

Expõe o `Base` declarativo dos modelos, cria o engine SQLite sob demanda e
fornece factories de sessão para telas, serviços e rotinas de migração.
"""

import shutil
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import DATABASE_URL, DATA_DIR, DB_PATH

Base = declarative_base()

_engine = None


def get_engine():
    """Retorna o engine SQLAlchemy configurado para o SQLite local.

    Cria a pasta de dados quando necessário e mantém um engine singleton por
    processo. `check_same_thread=False` evita conflito com o ciclo do Streamlit.
    """
    global _engine
    if _engine is None:
        DATA_DIR.mkdir(exist_ok=True)
        _engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_session_factory():
    """Cria uma factory de sessões vinculada ao engine da aplicação."""
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def run_schema_migrations(engine):
    """Adiciona colunas novas à tabela itens sem destruir dados existentes.

    Idempotente: ignora erros de "duplicate column name" do SQLite.
    Após adicionar as colunas, copia valores legados de estoque_minimo/ideal
    para os campos manuais/vigentes dos itens que já tinham valores definidos.
    """
    new_columns = [
        "ALTER TABLE itens ADD COLUMN estoque_minimo_sugerido INTEGER",
        "ALTER TABLE itens ADD COLUMN estoque_ideal_sugerido INTEGER",
        "ALTER TABLE itens ADD COLUMN estoque_minimo_manual INTEGER",
        "ALTER TABLE itens ADD COLUMN estoque_ideal_manual INTEGER",
        "ALTER TABLE itens ADD COLUMN data_definicao_minimo_manual DATETIME",
        "ALTER TABLE itens ADD COLUMN data_definicao_ideal_manual DATETIME",
        "ALTER TABLE itens ADD COLUMN estoque_minimo_vigente INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE itens ADD COLUMN estoque_ideal_vigente INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE itens ADD COLUMN origem_minimo VARCHAR(20)",
        "ALTER TABLE itens ADD COLUMN origem_ideal VARCHAR(20)",
        # Compras: urgência em solicitações e auditoria de sugestão na lista
        "ALTER TABLE solicitacoes_material ADD COLUMN urgente BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE itens_lista_compra ADD COLUMN motivo_sugestao TEXT",
        "ALTER TABLE itens_lista_compra RENAME COLUMN motivo TO observacao",
        # Fase 4: cabeçalho de pedido atômico
        "ALTER TABLE solicitacoes_material ADD COLUMN pedido_id INTEGER REFERENCES solicitacoes_pedido(id)",
        # Fase 5: canal de comunicação do setor
        "ALTER TABLE setores ADD COLUMN whatsapp VARCHAR(50)",
        # Fase 6: rastreamento de entrega de notificações WhatsApp por setor/ciclo
        "ALTER TABLE ciclo_solicitacao_setores ADD COLUMN envio_notificado_em DATETIME",
        "ALTER TABLE ciclo_solicitacao_setores ADD COLUMN falha_envio BOOLEAN DEFAULT 0",
        "ALTER TABLE ciclo_solicitacao_setores ADD COLUMN motivo_falha VARCHAR(200)",
        # Fase 7: website do fornecedor (URL do site, suporta {query} para busca)
        "ALTER TABLE fornecedores ADD COLUMN website VARCHAR(500)",
        # Fase 8 — deploy interno: tokens opacos para links públicos
        "ALTER TABLE ciclo_solicitacao_setores ADD COLUMN token TEXT",
        "ALTER TABLE orcamentos ADD COLUMN token_aprovacao TEXT",
    ]
    # Tabelas novas (CREATE TABLE IF NOT EXISTS é idempotente no SQLite)
    new_tables = [
        """
        CREATE TABLE IF NOT EXISTS solicitacoes_cotacao_fornecedor (
            id INTEGER PRIMARY KEY,
            orcamento_id INTEGER NOT NULL REFERENCES orcamentos(id),
            fornecedor_id INTEGER NOT NULL REFERENCES fornecedores(id),
            itens_json TEXT NOT NULL,
            prazo_resposta DATE,
            enviado_em DATETIME,
            wamid VARCHAR(100),
            status VARCHAR(20) NOT NULL DEFAULT 'ENVIADO'
        )
        """,
        # Fase 8: devoluções de material (novo fluxo pendente→reintegrada/descartada)
        """
        CREATE TABLE IF NOT EXISTS devolucoes_material (
            id INTEGER PRIMARY KEY,
            item_id INTEGER NOT NULL REFERENCES itens(id),
            setor_id INTEGER REFERENCES setores(id),
            quantidade INTEGER NOT NULL,
            motivo TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pendente',
            criado_em DATETIME,
            processado_em DATETIME
        )
        """,
    ]
    with engine.connect() as conn:
        for stmt in new_columns:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                # Coluna já existe — ignorar
                conn.rollback()

        for stmt in new_tables:
            conn.execute(text(stmt))
            conn.commit()

        # Índices únicos para tokens (WHERE token IS NOT NULL — não conflita com NULLs antigos)
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ciclo_setor_token "
            "ON ciclo_solicitacao_setores (token) WHERE token IS NOT NULL"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_orcamento_token_aprovacao "
            "ON orcamentos (token_aprovacao) WHERE token_aprovacao IS NOT NULL"
        ))
        conn.commit()

        # Migração de dados: trata estoque_minimo/ideal legados como valores manuais.
        # Só migra linhas onde estoque_minimo_vigente ainda está zerado E estoque_minimo > 0.
        conn.execute(text("""
            UPDATE itens
            SET
                estoque_minimo_manual   = estoque_minimo,
                estoque_ideal_manual    = estoque_ideal,
                estoque_minimo_vigente  = estoque_minimo,
                estoque_ideal_vigente   = estoque_ideal,
                origem_minimo           = 'Manual',
                origem_ideal            = 'Manual'
            WHERE estoque_minimo > 0
              AND (estoque_minimo_vigente IS NULL OR estoque_minimo_vigente = 0)
        """))
        conn.commit()

        # Garante unicidade de revisões por item/período: remove duplicatas mantendo
        # o registro mais antigo por (item_id, periodo_descricao), depois cria índice.
        conn.execute(text("""
            DELETE FROM revisoes_mensais
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM revisoes_mensais
                GROUP BY item_id, periodo_descricao
            )
        """))
        conn.commit()
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_revisao_item_periodo "
            "ON revisoes_mensais (item_id, periodo_descricao)"
        ))
        conn.commit()

        # Remove cabeçalhos de pedido órfãos (sem nenhuma solicitação vinculada).
        # deletar_solicitacao agora limpa o cabeçalho junto com o último item;
        # este DELETE idempotente saneia registros criados antes dessa correção.
        conn.execute(text("""
            DELETE FROM solicitacoes_pedido
            WHERE id NOT IN (
                SELECT DISTINCT pedido_id
                FROM solicitacoes_material
                WHERE pedido_id IS NOT NULL
            )
        """))
        conn.commit()

        # Invariante da Lista Final: item aprovado exige quantidade final >= 1.
        # Saneia registros gravados antes da validação: aprovados com quantidade
        # nula/zerada recebem a quantidade sugerida; sem sugerida válida, saem
        # da lista final. Compras avulsas zeradas voltam ao mínimo de 1.
        conn.execute(text("""
            UPDATE itens_lista_compra
            SET quantidade_final_definida = quantidade_sugerida
            WHERE incluir_na_lista_final = 1
              AND (quantidade_final_definida IS NULL OR quantidade_final_definida <= 0)
              AND quantidade_sugerida > 0
        """))
        conn.execute(text("""
            UPDATE itens_lista_compra
            SET incluir_na_lista_final = 0
            WHERE incluir_na_lista_final = 1
              AND (quantidade_final_definida IS NULL OR quantidade_final_definida <= 0)
        """))
        conn.execute(text(
            "UPDATE compras_avulsas SET quantidade = 1 "
            "WHERE quantidade IS NULL OR quantidade <= 0"
        ))
        conn.commit()

    _migrar_timestamps_para_hora_local(engine)


# Colunas DateTime gravadas com utcnow() antes da padronização em hora local.
# Campos digitados pelo usuário (prazo_resposta_em, data_cotacao, periodo_referencia,
# data_inicio/fim_analise) já estavam em hora local e NÃO entram aqui.
_COLUNAS_TZ_MIGRACAO = {
    "categorias": ["criado_em"],
    "itens": [
        "criado_em", "atualizado_em",
        "data_definicao_minimo_manual", "data_definicao_ideal_manual",
    ],
    "fornecedores": ["criado_em"],
    "precos_fornecedor": ["criado_em"],
    "setores": ["criado_em"],
    "movimentacoes": ["criado_em"],
    "snapshots_analise": ["criado_em"],
    "revisoes_mensais": ["criado_em"],
    "ciclos_solicitacao_material": ["criado_em", "abertura_em", "encerrado_em"],
    "ciclo_solicitacao_setores": [
        "respondido_em", "envio_notificado_em",
        "notificacao_lembrete_d2_em", "notificacao_prazo_proximo_em",
        "notificacao_encerramento_em", "notificacao_feedback_em",
    ],
    "solicitacoes_pedido": ["criado_em"],
    "solicitacoes_material": ["criado_em"],
    "compras_avulsas": ["criado_em"],
    "itens_lista_compra": ["criado_em", "atualizado_em"],
    "importacoes": ["criado_em"],
}


def _migrar_timestamps_para_hora_local(engine):
    """Migração única: converte timestamps históricos de UTC para hora local (-3h).

    O sistema passou a gravar tudo em hora de Brasília (core/tempo.py); registros
    antigos foram gravados com utcnow() e ficariam 3h adiantados. Idempotente via
    marcador 'tz_local_migrada' na tabela schema_meta — nunca roda duas vezes.
    Cria backup do arquivo SQLite antes de alterar qualquer linha.
    """
    from core import tempo

    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_meta (chave TEXT PRIMARY KEY, valor TEXT)"
        ))
        conn.commit()

        ja_migrado = conn.execute(text(
            "SELECT 1 FROM schema_meta WHERE chave = 'tz_local_migrada'"
        )).first()
        if ja_migrado:
            return

        # Backup do arquivo antes da única operação destrutiva do upgrade.
        # Usa o caminho do próprio engine (não DB_PATH fixo) para também
        # funcionar corretamente em bancos de teste/cópias.
        db_file = Path(engine.url.database) if engine.url.database else DB_PATH
        if db_file.exists():
            sufixo = tempo.agora().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(db_file, db_file.with_name(f"{db_file.stem}_pre_tz_{sufixo}.bak"))

        # Transação única: ou todas as colunas migram junto com o marcador,
        # ou nada é alterado (uma falha no meio não deixa migração parcial).
        for tabela, colunas in _COLUNAS_TZ_MIGRACAO.items():
            for col in colunas:
                conn.execute(text(
                    f"UPDATE {tabela} SET {col} = datetime({col}, '-3 hours') "
                    f"WHERE {col} IS NOT NULL"
                ))
        conn.execute(text(
            "INSERT INTO schema_meta (chave, valor) VALUES ('tz_local_migrada', :v)"
        ), {"v": tempo.agora().isoformat()})
        conn.commit()


def init_db():
    """Cria as tabelas do banco caso elas ainda não existam e executa migrações de schema."""
    from core import models  # noqa: F401 — registra todos os modelos no Base
    engine = get_engine()
    Base.metadata.create_all(engine)
    run_schema_migrations(engine)
