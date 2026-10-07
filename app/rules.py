"""Regras de negócio: cadastro, farol e prioridade. Fonte única de verdade (servidor)."""
import re
import unicodedata
from datetime import date, datetime

NIVEIS = {"LE": 3, "ME": 2, "Growth": 2, "Legado": 1}
TIPOS = ["Implantação", "Integração", "Melhoria", "Acompanhamento", "Risco"]
BLOQUEIOS = ["Aguardando cliente", "Aguardando AM", "Aguardando engenharia",
             "Aguardando produto", "Aguardando terceiro", "Outro"]
TETO_LEGADO = 5900
COMPLEXIDADES = ["Baixa", "Média", "Alta"]


def _sa(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn")


def hk(s):
    return re.sub(r"[^a-z]", "", _sa(s).lower())


def norm(s):
    s = re.split(r"[|/]", _sa(s))[0].lower()
    s = re.sub(r"\b(ltda|sa|me|eireli)\b", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def parse_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    try:
        return date(int(m[3]), int(m[2]), int(m[1])) if m else date.fromisoformat(s[:10])
    except ValueError:
        raise ValueError("Data inválida (use dd/mm/aaaa)")


def parse_mrr(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[R$\s]", "", str(v or ""))
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def _ajuste(v):
    try:
        return max(-1, min(1, int(v or 0)))
    except (ValueError, TypeError):
        return 0


def _txt(d, k):
    return str(d.get(k) or "").strip() or None


def valida_conta(d, lookup):
    """lookup: {nome_norm: nome} das contas existentes (sem a própria, em edição)."""
    e, w = [], []
    nome = str(d.get("nome") or "").strip()
    if not nome:
        e.append("Nome obrigatório")
    nivel = next((k for k in NIVEIS if hk(k) == hk(d.get("nivel"))), None)
    if not nivel:
        e.append("Nível deve ser LE, ME, Growth ou Legado")
    try:
        mrr = parse_mrr(d.get("mrr"))
        if mrr < 0:
            raise ValueError
    except (ValueError, TypeError):
        mrr = None
        e.append("MRR inválido (número ≥ 0, ex.: 5.940,00)")
    k = norm(nome)
    if k:
        if k in lookup:
            e.append("Conta já cadastrada")
        else:
            p = next((n for kk, n in lookup.items() if kk and k.startswith(kk + " ")), None)
            if p:
                w.append(f"Possível contrato da conta {p}")
    if nivel == "Legado" and mrr is not None and mrr >= TETO_LEGADO:
        w.append("MRR acima do teto de Legado (R$ 5.900): revisar nível")
    seg = _txt(d, "segmento")
    if not seg:
        w.append("Segmento não informado")
    cx = None
    if _txt(d, "complexidade"):
        cx = next((c for c in COMPLEXIDADES if hk(c) == hk(d.get("complexidade"))), None)
        if not cx:
            e.append("Complexidade deve ser: " + ", ".join(COMPLEXIDADES))
    else:
        w.append("Complexidade não informada")
    cnpj = re.sub(r"\D", "", str(d.get("cnpj") or "")) or None
    if cnpj and len(cnpj) != 14:
        e.append("CNPJ deve ter 14 dígitos")
    email = _txt(d, "contato_email")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        e.append("E-mail do contato inválido")
    datas = {}
    for campo, rot in (("data_inicio", "Início do contrato"), ("ultimo_contato", "Último contato"), ("proximo_contato", "Próximo contato")):
        try:
            datas[campo] = parse_date(d.get(campo))
        except ValueError:
            datas[campo] = None
            e.append(f"{rot}: data inválida (use dd/mm/aaaa)")
    return e, w, dict(nome=nome, nome_norm=k, nivel=nivel, mrr=mrr, segmento=seg, nota=_txt(d, "nota"),
                      ajuste_impacto=_ajuste(d.get("ajuste_impacto")), churn=bool(d.get("churn", False)),
                      razao_social=_txt(d, "razao_social"), cnpj=cnpj, complexidade=cx, erp=_txt(d, "erp"),
                      integracoes=_txt(d, "integracoes"), contato_nome=_txt(d, "contato_nome"),
                      contato_email=email, contato_telefone=_txt(d, "contato_telefone"), **datas)


def valida_projeto(d, lookup, existentes, checar_dup=True):
    """lookup: {conta_norm: nome}; existentes: {(conta_norm, projeto_norm)}."""
    e, w = [], []
    ck = norm(d.get("conta"))
    conta = lookup.get(ck)
    if not conta:
        e.append("Conta não cadastrada: cadastre a conta antes")
    nome = str(d.get("nome") or "").strip()
    if not nome:
        e.append("Projeto obrigatório")
    tipo = next((t for t in TIPOS if hk(t) == hk(d.get("tipo"))), None)
    if not tipo:
        e.append("Tipo deve ser: " + ", ".join(TIPOS))
    try:
        prazo = parse_date(d.get("prazo"))
    except ValueError as ex:
        prazo = None
        e.append(str(ex))
    dono = str(d.get("bloqueio_dono") or "").strip()
    if dono:
        canon = next((b for b in BLOQUEIOS if hk(b) == hk(dono)), None)
        if not canon:
            e.append("Bloqueio deve ser: " + ", ".join(BLOQUEIOS))
        dono = canon
    motivo = str(d.get("bloqueio_motivo") or "").strip() or None
    if dono and not motivo:
        e.append("Bloqueio exige motivo")
    if not dono:
        dono, motivo = None, None
    if checar_dup and conta and nome and (ck, norm(nome)) in existentes:
        e.append("Projeto já cadastrado nesta conta")
    if not e and not prazo and tipo not in ("Acompanhamento", "Risco"):
        w.append("Sem prazo: farol ficará cinza")
    return e, w, dict(conta_nome=conta, conta_norm=ck, nome=nome, nome_norm=norm(nome), tipo=tipo,
                      situacao=str(d.get("situacao") or "").strip() or None, critico=bool(d.get("critico", False)),
                      bloqueio_dono=dono, bloqueio_motivo=motivo, prazo=prazo,
                      proxima_acao=str(d.get("proxima_acao") or "").strip() or None,
                      ajuste_impacto=_ajuste(d.get("ajuste_impacto")))


def farol(p, hoje):
    d = (hoje - p.ultima_atualizacao).days
    pz = (p.prazo - hoje).days if p.prazo else None
    if d > 7:
        return "C", f"Sem atualização há {d} dias"
    if p.critico:
        return "R", p.situacao or "Situação crítica"
    if pz is not None and pz < 0:
        return ("R" if pz < -5 else "Y"), f"Atraso de {-pz} dias"
    if p.bloqueio_dono:
        return "Y", p.bloqueio_motivo or p.bloqueio_dono
    if pz is not None and pz <= 7:
        return "Y", f"Prazo em {pz} dias"
    if d >= 4:
        return "Y", f"Sem atualização há {d} dias"
    if pz is None and p.tipo != "Acompanhamento":
        return "C", "Sem prazo definido: sem informação suficiente"
    return "G", "Sem impedimentos informados"


def prioridade(p, conta, hoje):
    fat = []
    imp = min(3, max(1, NIVEIS.get(conta.nivel, 1) + (p.ajuste_impacto or 0)))
    fat.append(f"Conta {conta.nivel} ({conta.nome})" + (f", ajuste manual {p.ajuste_impacto:+d}" if p.ajuste_impacto else ""))
    pz = (p.prazo - hoje).days if p.prazo else None
    if p.critico:
        urg = 3
        fat.append("Situação crítica")
    elif pz is not None:
        urg = 3 if pz <= 2 else 2 if pz <= 7 else 1
        fat.append(f"Prazo vencido há {-pz} dias" if pz < 0 else f"Prazo em {pz} dias")
    else:
        urg = 1
        fat.append("Prazo não informado (urgência mínima)")
    if p.critico or (pz is not None and pz < 0):
        risco = 3
    elif p.bloqueio_dono:
        risco = 2
        fat.append(f"{p.bloqueio_dono}: {p.bloqueio_motivo}")
    else:
        risco = 1
    s = imp + urg + risco
    nivel = "crítica" if s >= 7 else "alta" if s >= 5 else "média" if s >= 3 else "baixa"
    ordem = s * 1e6 + risco * 1e5 + (max(0, 30 - pz) if pz is not None else 0) * 100 + conta.mrr / 1e4
    return dict(score=s, nivel=nivel, impacto=imp, urgencia=urg, risco=risco, fatores=fat, ordem=ordem)
