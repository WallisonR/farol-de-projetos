import os
from datetime import date, datetime
from sqlalchemy import (create_engine, ForeignKey, String, Text, Date, DateTime, Boolean,
                        Integer, Numeric, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from sqlalchemy.pool import NullPool

RAW = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""
NA_VERCEL = bool(os.getenv("VERCEL"))
SEM_BANCO = NA_VERCEL and not RAW          # no Vercel o disco não persiste: exige Postgres
URL = RAW or ("sqlite:////tmp/farol.db" if NA_VERCEL else "sqlite:///./farol.db")
for _pref in ("postgres://", "postgresql://"):   # fixa o driver psycopg2 (o mesmo do requirements.txt)
    if URL.startswith(_pref):
        URL = "postgresql+psycopg2://" + URL[len(_pref):]
if URL.startswith("postgresql"):           # remove parâmetros que o psycopg2 não aceita (ex.: supa=)
    _s = urlsplit(URL)
    URL = urlunsplit(_s._replace(query=urlencode([(k, v) for k, v in parse_qsl(_s.query) if k != "supa"])))
if URL.startswith("sqlite"):
    _kw = {"connect_args": {"check_same_thread": False}}
else:
    _kw = {"pool_pre_ping": True}
    if NA_VERCEL:
        _kw["poolclass"] = NullPool         # serverless: sem pool de conexões entre execuções
engine = create_engine(URL, **_kw)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True)
    nome: Mapped[str] = mapped_column(String(120))
    senha_hash: Mapped[str] = mapped_column(String(300))
    papel: Mapped[str] = mapped_column(String(10), default="am")  # admin | am
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Conta(Base):
    __tablename__ = "contas"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    nome_norm: Mapped[str] = mapped_column(String(200), unique=True)
    nivel: Mapped[str] = mapped_column(String(10))
    mrr: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False))
    segmento: Mapped[str | None] = mapped_column(String(120), nullable=True)
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)
    churn: Mapped[bool] = mapped_column(Boolean, default=False)
    ajuste_impacto: Mapped[int] = mapped_column(Integer, default=0)
    razao_social: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complexidade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    erp: Mapped[str | None] = mapped_column(String(120), nullable=True)
    integracoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    contato_nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contato_email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contato_telefone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    ultimo_contato: Mapped[date | None] = mapped_column(Date, nullable=True)
    proximo_contato: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsavel_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    projetos = relationship("Projeto", back_populates="conta")


class Projeto(Base):
    __tablename__ = "projetos"
    __table_args__ = (UniqueConstraint("conta_id", "nome_norm"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))
    nome: Mapped[str] = mapped_column(String(200))
    nome_norm: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(30))
    situacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    critico: Mapped[bool] = mapped_column(Boolean, default=False)
    bloqueio_dono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bloqueio_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    prazo: Mapped[date | None] = mapped_column(Date, nullable=True)
    proxima_acao: Mapped[str | None] = mapped_column(Text, nullable=True)
    ajuste_impacto: Mapped[int] = mapped_column(Integer, default=0)
    ultima_atualizacao: Mapped[date] = mapped_column(Date, default=date.today)
    conta = relationship("Conta", back_populates="projetos")


class Historico(Base):
    __tablename__ = "historico"
    id: Mapped[int] = mapped_column(primary_key=True)
    em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    usuario: Mapped[str] = mapped_column(String(80), default="api")
    entidade: Mapped[str] = mapped_column(String(20))
    entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rotulo: Mapped[str] = mapped_column(String(300), default="")
    responsavel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campo: Mapped[str] = mapped_column(String(60))
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_novo: Mapped[str | None] = mapped_column(Text, nullable=True)


class Importacao(Base):
    __tablename__ = "importacoes"
    id: Mapped[int] = mapped_column(primary_key=True)
    em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    arquivo: Mapped[str] = mapped_column(String(300))
    linhas_ok: Mapped[int] = mapped_column(Integer)
    linhas_erro: Mapped[int] = mapped_column(Integer)
    usuario: Mapped[str] = mapped_column(String(80), default="api")


NOVAS_COLUNAS = {"contas": {"razao_social": "VARCHAR(200)", "cnpj": "VARCHAR(20)", "complexidade": "VARCHAR(10)",
                            "erp": "VARCHAR(120)", "integracoes": "TEXT", "contato_nome": "VARCHAR(120)",
                            "contato_email": "VARCHAR(160)", "contato_telefone": "VARCHAR(40)", "data_inicio": "DATE",
                            "ultimo_contato": "DATE", "proximo_contato": "DATE", "responsavel_id": "INTEGER"},
                 "historico": {"responsavel_id": "INTEGER"}}


def migrar():
    """Adiciona colunas novas em bancos criados por versões anteriores (create_all não altera tabelas existentes)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for tabela, cols in NOVAS_COLUNAS.items():
        if not insp.has_table(tabela):
            continue
        existentes = {c["name"] for c in insp.get_columns(tabela)}
        for nome, tipo in cols.items():
            if nome not in existentes:
                try:
                    with engine.begin() as cx:
                        cx.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}"))
                except Exception:
                    pass  # outra instância adicionou ao mesmo tempo
