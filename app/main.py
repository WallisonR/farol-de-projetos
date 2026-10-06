import csv, io, json, os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File, Query, APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from . import rules as R
from sqlalchemy.exc import IntegrityError, ProgrammingError
from .db import Base, engine, SessionLocal, SEM_BANCO, URL, Conta, Projeto, Historico, Importacao
from .seed import seed

PUBLIC = Path(__file__).parent.parent / "public"
_pronto = False


def iniciar():
    """Cria as tabelas e faz a carga inicial uma vez por instância (idempotente; seguro em serverless)."""
    global _pronto
    if _pronto:
        return
    try:
        Base.metadata.create_all(engine)
    except (ProgrammingError, IntegrityError):
        pass  # outra instância criou ao mesmo tempo
    if os.getenv("SEED", "1") != "0":
        with SessionLocal() as db:
            try:
                seed(db)
            except IntegrityError:
                db.rollback()
    _pronto = True


@asynccontextmanager
async def lifespan(app):
    if not SEM_BANCO:
        iniciar()
    yield


app = FastAPI(title="Farol da Carteira", version="1.0", lifespan=lifespan)


def get_db():
    if SEM_BANCO:
        raise HTTPException(503, "Banco não configurado: defina DATABASE_URL (PostgreSQL) nas variáveis de ambiente do Vercel")
    iniciar()
    with SessionLocal() as db:
        yield db


def auth(authorization: str | None = Header(None)):
    token = os.getenv("API_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "Token inválido ou ausente")


def quem(x_usuario: str | None = Header(None)):
    return (x_usuario or "api")[:80]


api = APIRouter(prefix="/api", dependencies=[Depends(auth)])


# ---------- schemas ----------
class ContaIn(BaseModel):
    nome: str
    nivel: str
    mrr: float | str
    segmento: str | None = None
    nota: str | None = None
    ajuste_impacto: int = 0


class ContaPatch(BaseModel):
    nome: str | None = None
    nivel: str | None = None
    mrr: float | str | None = None
    segmento: str | None = None
    nota: str | None = None
    ajuste_impacto: int | None = None
    churn: bool | None = None


class ProjetoIn(BaseModel):
    conta_id: int | None = None
    conta: str | None = None
    nome: str
    tipo: str
    situacao: str | None = None
    critico: bool = False
    bloqueio_dono: str | None = None
    bloqueio_motivo: str | None = None
    prazo: str | None = None
    proxima_acao: str | None = None
    ajuste_impacto: int = 0


class ProjetoPatch(BaseModel):
    nome: str | None = None
    tipo: str | None = None
    situacao: str | None = None
    critico: bool | None = None
    bloqueio_dono: str | None = None
    bloqueio_motivo: str | None = None
    prazo: str | None = None
    proxima_acao: str | None = None
    ajuste_impacto: int | None = None


class Evento(ProjetoPatch):
    conta: str
    projeto: str


# ---------- helpers ----------
def falha(e, w=()):
    raise HTTPException(422, detail={"erros": list(e), "avisos": list(w)})


def lookup_contas(db, excluir=None):
    return {c.nome_norm: c.nome for c in db.scalars(select(Conta)) if c.id != excluir}


def existentes(db):
    rows = db.execute(select(Conta.nome_norm, Projeto.nome_norm).join(Projeto, Projeto.conta_id == Conta.id)).all()
    return {(a, b) for a, b in rows}


def log(db, user, ent, eid, rotulo, campo, ant, novo):
    db.add(Historico(usuario=user, entidade=ent, entidade_id=eid, rotulo=rotulo, campo=campo,
                     valor_anterior=None if ant is None else str(ant), valor_novo=None if novo is None else str(novo)))


def c_out(c, n=None):
    return dict(id=c.id, nome=c.nome, nivel=c.nivel, mrr=c.mrr, segmento=c.segmento, nota=c.nota,
                churn=c.churn, ajuste_impacto=c.ajuste_impacto, n_projetos=n)


def p_out(p, hoje):
    cor, mot = R.farol(p, hoje)
    return dict(id=p.id, conta_id=p.conta_id, conta=p.conta.nome, nome=p.nome, tipo=p.tipo, situacao=p.situacao,
                critico=p.critico, bloqueio_dono=p.bloqueio_dono, bloqueio_motivo=p.bloqueio_motivo,
                prazo=p.prazo.isoformat() if p.prazo else None, proxima_acao=p.proxima_acao,
                ajuste_impacto=p.ajuste_impacto, ultima_atualizacao=p.ultima_atualizacao.isoformat(),
                farol=dict(cor=cor, motivo=mot), prioridade=R.prioridade(p, p.conta, hoje))


def projetos_ativos(db):
    q = select(Projeto).join(Conta).options(joinedload(Projeto.conta)).where(Conta.churn == False)  # noqa: E712
    return list(db.scalars(q).unique())


def criar_conta(db, l, user):
    c = Conta(**l)
    db.add(c); db.flush()
    log(db, user, "conta", c.id, c.nome, "conta", None, "cadastrada")
    return c


def criar_projeto(db, l, user):
    conta = db.scalar(select(Conta).where(Conta.nome_norm == l["conta_norm"]))
    p = Projeto(conta_id=conta.id, nome=l["nome"], nome_norm=l["nome_norm"], tipo=l["tipo"], situacao=l["situacao"],
                critico=l["critico"], bloqueio_dono=l["bloqueio_dono"], bloqueio_motivo=l["bloqueio_motivo"],
                prazo=l["prazo"], proxima_acao=l["proxima_acao"], ajuste_impacto=l["ajuste_impacto"],
                ultima_atualizacao=date.today())
    db.add(p); db.flush()
    log(db, user, "projeto", p.id, f"{conta.nome} / {p.nome}", "projeto", None, "cadastrado")
    return p


def atualizar_projeto(db, p, mudancas, user):
    cur = dict(conta=p.conta.nome, nome=p.nome, tipo=p.tipo, situacao=p.situacao, critico=p.critico,
               bloqueio_dono=p.bloqueio_dono, bloqueio_motivo=p.bloqueio_motivo, prazo=p.prazo,
               proxima_acao=p.proxima_acao, ajuste_impacto=p.ajuste_impacto)
    cur.update(mudancas)
    ex = existentes(db) - {(R.norm(p.conta.nome), p.nome_norm)}
    e, w, l = R.valida_projeto(cur, {R.norm(p.conta.nome): p.conta.nome}, ex)
    if e:
        falha(e, w)
    hoje = date.today()
    antes = R.farol(p, hoje)[0]
    rotulo = f"{p.conta.nome} / {p.nome}"
    for k in ("nome", "nome_norm", "tipo", "situacao", "critico", "bloqueio_dono", "bloqueio_motivo", "prazo",
              "proxima_acao", "ajuste_impacto"):
        if getattr(p, k) != l[k]:
            if k != "nome_norm":
                log(db, user, "projeto", p.id, rotulo, k, getattr(p, k), l[k])
            setattr(p, k, l[k])
    p.ultima_atualizacao = hoje
    depois = R.farol(p, hoje)[0]
    if antes != depois:
        log(db, user, "projeto", p.id, rotulo, "farol", antes, depois)
    return w


# ---------- rotas: contas ----------
@api.get("/contas")
def listar_contas(db: Session = Depends(get_db), q: str | None = None, nivel: str | None = None):
    hoje_n = {}
    for p in db.scalars(select(Projeto)):
        hoje_n[p.conta_id] = hoje_n.get(p.conta_id, 0) + 1
    out = [c_out(c, hoje_n.get(c.id, 0)) for c in db.scalars(select(Conta).order_by(Conta.mrr.desc()))]
    if nivel:
        out = [c for c in out if c["nivel"] == nivel]
    if q:
        out = [c for c in out if R.norm(q) in R.norm(c["nome"] + " " + (c["segmento"] or ""))]
    return out


@api.post("/contas", status_code=201)
def cadastrar_conta(body: ContaIn, db: Session = Depends(get_db), user: str = Depends(quem)):
    e, w, l = R.valida_conta(body.model_dump(), lookup_contas(db))
    if e:
        falha(e, w)
    c = criar_conta(db, l, user)
    db.commit()
    return dict(c_out(c), avisos=w)


@api.get("/contas/{cid}")
def detalhe_conta(cid: int, db: Session = Depends(get_db)):
    c = db.get(Conta, cid)
    if not c:
        raise HTTPException(404, "Conta não encontrada")
    hoje = date.today()
    ps = [p_out(p, hoje) for p in db.scalars(select(Projeto).where(Projeto.conta_id == cid).options(joinedload(Projeto.conta)))]
    return dict(c_out(c, len(ps)), projetos=ps)


@api.patch("/contas/{cid}")
def editar_conta(cid: int, body: ContaPatch, db: Session = Depends(get_db), user: str = Depends(quem)):
    c = db.get(Conta, cid)
    if not c:
        raise HTTPException(404, "Conta não encontrada")
    cur = dict(nome=c.nome, nivel=c.nivel, mrr=c.mrr, segmento=c.segmento, nota=c.nota,
               ajuste_impacto=c.ajuste_impacto, churn=c.churn)
    cur.update(body.model_dump(exclude_unset=True))
    e, w, l = R.valida_conta(cur, lookup_contas(db, excluir=cid))
    if e:
        falha(e, w)
    for k, v in l.items():
        if getattr(c, k) != v:
            if k != "nome_norm":
                log(db, user, "conta", c.id, c.nome, k, getattr(c, k), v)
            setattr(c, k, v)
    db.commit()
    return dict(c_out(c), avisos=w)


# ---------- rotas: projetos ----------
@api.get("/projetos")
def listar_projetos(db: Session = Depends(get_db), conta_id: int | None = None, tipo: str | None = None,
                    farol: str | None = None, q: str | None = None, bloqueado: bool | None = None):
    hoje = date.today()
    out = [p_out(p, hoje) for p in projetos_ativos(db)]
    if conta_id:
        out = [p for p in out if p["conta_id"] == conta_id]
    if tipo:
        out = [p for p in out if p["tipo"] == tipo]
    if farol:
        out = [p for p in out if p["farol"]["cor"] == farol.upper()]
    if bloqueado is not None:
        out = [p for p in out if bool(p["bloqueio_dono"]) == bloqueado]
    if q:
        out = [p for p in out if R.norm(q) in R.norm(p["conta"] + " " + p["nome"])]
    return sorted(out, key=lambda p: -p["prioridade"]["ordem"])


@api.post("/projetos", status_code=201)
def cadastrar_projeto(body: ProjetoIn, db: Session = Depends(get_db), user: str = Depends(quem)):
    d = body.model_dump()
    if d["conta_id"]:
        c = db.get(Conta, d["conta_id"])
        d["conta"] = c.nome if c else None
    e, w, l = R.valida_projeto(d, lookup_contas(db), existentes(db))
    if e:
        falha(e, w)
    p = criar_projeto(db, l, user)
    db.commit()
    db.refresh(p)
    return dict(p_out(p, date.today()), avisos=w)


@api.get("/projetos/{pid}")
def detalhe_projeto(pid: int, db: Session = Depends(get_db)):
    p = db.get(Projeto, pid)
    if not p:
        raise HTTPException(404, "Projeto não encontrado")
    h = db.scalars(select(Historico).where(Historico.entidade == "projeto", Historico.entidade_id == pid)
                   .order_by(Historico.id.desc()).limit(100))
    return dict(p_out(p, date.today()), historico=[hist_out(x) for x in h])


@api.patch("/projetos/{pid}")
def editar_projeto(pid: int, body: ProjetoPatch, db: Session = Depends(get_db), user: str = Depends(quem)):
    p = db.get(Projeto, pid)
    if not p:
        raise HTTPException(404, "Projeto não encontrado")
    w = atualizar_projeto(db, p, body.model_dump(exclude_unset=True), user)
    db.commit()
    return dict(p_out(p, date.today()), avisos=w)


# ---------- carteira e histórico ----------
@api.get("/carteira/farol")
def carteira(db: Session = Depends(get_db)):
    hoje = date.today()
    ps = sorted((p_out(p, hoje) for p in projetos_ativos(db)), key=lambda p: -p["prioridade"]["ordem"])
    contas = [c_out(c, sum(1 for p in ps if p["conta_id"] == c.id)) for c in db.scalars(select(Conta).order_by(Conta.mrr.desc()))]
    ativas = [c for c in contas if not c["churn"]]
    cnt = lambda cor: sum(1 for p in ps if p["farol"]["cor"] == cor)  # noqa: E731
    dono = {}
    for p in ps:
        if p["bloqueio_dono"]:
            dono[p["bloqueio_dono"]] = dono.get(p["bloqueio_dono"], 0) + 1
    resumo = dict(contas_ativas=len(ativas), projetos=len(ps), vermelho=cnt("R"), amarelo=cnt("Y"), verde=cnt("G"),
                  cinza=cnt("C"), bloqueados=sum(1 for p in ps if p["bloqueio_dono"]),
                  atrasados=sum(1 for p in ps if p["prazo"] and p["prazo"] < hoje.isoformat()),
                  mrr_ativo=round(sum(c["mrr"] for c in ativas), 2), bloqueios_por_dono=dono)
    return dict(hoje=hoje.isoformat(), resumo=resumo, contas=contas, projetos=ps)


def hist_out(h):
    return dict(id=h.id, em=h.em.isoformat(), usuario=h.usuario, entidade=h.entidade, rotulo=h.rotulo, campo=h.campo,
                valor_anterior=h.valor_anterior, valor_novo=h.valor_novo)


@api.get("/historico")
def historico(db: Session = Depends(get_db), limit: int = Query(200, le=1000)):
    return [hist_out(h) for h in db.scalars(select(Historico).order_by(Historico.id.desc()).limit(limit))]


# ---------- importação ----------
MC = {"nome": ["nome", "conta", "cliente"], "nivel": ["nivel", "tier"], "mrr": ["mrr", "receita"],
      "segmento": ["segmento"], "nota": ["observacoes", "obs", "nota"]}
MP = {"conta": ["conta", "cliente"], "nome": ["projeto", "nomedoprojeto"], "tipo": ["tipo"],
      "situacao": ["situacao", "status"], "prazo": ["prazo"], "proxima_acao": ["proximaacao"],
      "bloqueio_dono": ["bloqueio"], "bloqueio_motivo": ["motivodobloqueio", "motivo"], "critico": ["critico"]}


def mapear(row, M):
    o = {}
    for k, v in row.items():
        h = R.hk(k)
        for f, nomes in M.items():
            if h in nomes and f not in o:
                o[f] = v
    if "critico" in o:
        o["critico"] = R.hk(o["critico"]) in ("sim", "s", "true", "x", "verdadeiro") or str(o["critico"]).strip() == "1"
    return o


def _tipo(rows):
    return "p" if any(R.hk(k) == "projeto" for k in rows[0]) else "c"


def ler_arquivo(nome, dados):
    n = nome.lower()
    try:
        if n.endswith(".json"):
            j = json.loads(dados.decode("utf-8-sig"))
            return [("c", j.get("contas", [])), ("p", j.get("projetos", []))]
        if n.endswith(".csv"):
            try:
                t = dados.decode("utf-8-sig")
            except UnicodeDecodeError:
                t = dados.decode("latin-1")
            try:
                dial = csv.Sniffer().sniff(t[:2000], delimiters=",;\t")
            except csv.Error:
                dial = csv.excel
            rows = list(csv.DictReader(io.StringIO(t), dialect=dial))
            return [(_tipo(rows), rows)] if rows else []
        if n.endswith((".xlsx", ".xlsm")):
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(dados), data_only=True, read_only=True)
            out = []
            for ws in wb.worksheets:
                it = ws.iter_rows(values_only=True)
                hdr = next(it, None)
                if not hdr:
                    continue
                rows = [{str(h): v for h, v in zip(hdr, r) if h is not None} for r in it
                        if any(x not in (None, "") for x in r)]
                if rows:
                    out.append((_tipo(rows), rows))
            return out
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(400, f"Não foi possível ler o arquivo: {ex}")
    raise HTTPException(400, "Formato não suportado. Use .xlsx, .csv ou .json (salve .xls como .xlsx)")


def processar(db, sets):
    lk, ex, itens = lookup_contas(db), existentes(db), []
    for kind, rows in sorted(sets, key=lambda s: s[0]):  # contas antes de projetos
        for i, r in enumerate(rows, 2):
            if kind == "c":
                e, w, l = R.valida_conta(mapear(r, MC), lk)
                if not e:
                    lk[l["nome_norm"]] = l["nome"]
                itens.append(dict(tipo="conta", linha=i, registro=l["nome"] or "?", erros=e, avisos=w, _l=l))
            else:
                o = mapear(r, MP)
                e, w, l = R.valida_projeto(o, lk, ex)
                if not e:
                    ex.add((l["conta_norm"], l["nome_norm"]))
                itens.append(dict(tipo="projeto", linha=i, registro=f'{l["conta_nome"] or o.get("conta") or "?"} / {l["nome"] or "?"}',
                                  erros=e, avisos=w, _l=l))
    return itens


@api.post("/importacoes")
async def importar(arquivo: UploadFile = File(...), dry_run: bool = False, db: Session = Depends(get_db),
                   user: str = Depends(quem)):
    sets = ler_arquivo(arquivo.filename or "", await arquivo.read())
    itens = processar(db, sets)
    ok = [x for x in itens if not x["erros"]]
    if not itens:
        raise HTTPException(400, "Nenhuma linha encontrada no arquivo")
    if not dry_run and ok:
        for x in ok:
            if x["tipo"] == "conta":
                criar_conta(db, x["_l"], user)
        db.flush()
        for x in ok:
            if x["tipo"] == "projeto":
                criar_projeto(db, x["_l"], user)
        db.add(Importacao(arquivo=arquivo.filename or "", linhas_ok=len(ok), linhas_erro=len(itens) - len(ok), usuario=user))
        db.commit()
    for x in itens:
        x.pop("_l")
    return dict(arquivo=arquivo.filename, dry_run=dry_run, gravados=0 if dry_run else len(ok), validos=len(ok),
                com_erro=len(itens) - len(ok), linhas=itens)


# ---------- webhook ----------
@api.post("/webhooks/projetos")
def webhook(ev: Evento, db: Session = Depends(get_db), user: str = Depends(quem)):
    ck, pk = R.norm(ev.conta), R.norm(ev.projeto)
    conta = db.scalar(select(Conta).where(Conta.nome_norm == ck))
    if not conta:
        falha(["Conta não cadastrada: cadastre a conta antes"])
    p = db.scalar(select(Projeto).where(Projeto.conta_id == conta.id, Projeto.nome_norm == pk))
    mud = ev.model_dump(exclude_unset=True, exclude={"conta", "projeto"})
    if p:
        w = atualizar_projeto(db, p, mud, user)
        acao = "atualizado"
    else:
        d = dict(mud, conta=conta.nome, nome=ev.projeto)
        e, w, l = R.valida_projeto(d, {ck: conta.nome}, existentes(db))
        if e:
            falha(e, w)
        p = criar_projeto(db, l, user)
        acao = "criado"
    db.commit()
    return dict(acao=acao, projeto=p_out(p, date.today()), avisos=w)


@api.get("/health", include_in_schema=False)
def health():
    return {"ok": not SEM_BANCO, "banco": URL.split(":")[0], "configurado": not SEM_BANCO}


app.include_router(api)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(PUBLIC / "index.html")
