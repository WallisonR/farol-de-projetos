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
