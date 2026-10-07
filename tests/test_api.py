import io, os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ["ADMIN_SENHA"] = "senhaForte123"
os.environ.pop("API_TOKEN", None)
from datetime import date, timedelta
from fastapi.testclient import TestClient
from openpyxl import Workbook
from app.main import app
import app.main as m

ADM = "wallison@chatbotmaker.io"


def entrar(c, email=ADM, senha="senhaForte123"):
    r = c.post("/api/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = "Bearer " + r.json()["token"]
    return c


def sair(c):
    c.headers.pop("Authorization", None)


def test_login_e_protecao():
    with TestClient(app) as c:
        assert c.get("/api/contas").status_code == 401
        assert c.get("/api/carteira/farol").status_code == 401
        assert c.post("/api/auth/login", json={"email": ADM, "senha": "errada"}).status_code == 401
        assert c.post("/api/auth/login", json={"email": "ninguem@x.com", "senha": "x"}).status_code == 401
        r = entrar(c).get("/api/auth/eu").json()
        assert r["email"] == ADM and r["papel"] == "admin"
        c.headers["Authorization"] = "Bearer lixo"
        assert c.get("/api/contas").status_code == 401
        assert c.get("/").status_code == 200 and c.get("/api/health").json()["admin_senha_definida"]


def test_seed_e_carteira():
    with TestClient(app) as c0:
        c = entrar(c0)
        d = c.get("/api/carteira/farol").json()
        assert d["resumo"]["contas_ativas"] == 25 and d["resumo"]["projetos"] == 14
        cores = {p["conta"] + "/" + p["nome"]: p["farol"]["cor"] for p in d["projetos"]}
        assert cores["Omni Pet/Preço Meta"] == "R" and cores["ADITEK/Implantação multi-times"] == "Y"
        assert cores["Bionnovation/Operação pós-ERP"] == "G" and cores["CASA RENA/Implantação"] == "C"
        assert all(p["farol"]["motivo"] for p in d["projetos"]) and d["projetos"][0]["prioridade"]["fatores"]
        assert d["responsaveis"][0]["nome"] == "Wallison Rocha"


def test_cadastro_conta_completo_e_filtros():
    with TestClient(app) as c0:
        c = entrar(c0)
        corpo = {"nome": "Loja Nova", "nivel": "Growth", "mrr": "7.500,50", "segmento": "Varejo", "complexidade": "alta",
                 "razao_social": "Loja Nova SA", "cnpj": "12.345.678/0001-90", "erp": "Protheus", "integracoes": "ERP, marketplace",
                 "contato_nome": "Ana", "contato_email": "ana@loja.com", "contato_telefone": "11 99999-0000",
                 "data_inicio": "01/08/2026", "ultimo_contato": "2026-09-20", "proximo_contato": "15/10/2026"}
        r = c.post("/api/contas", json=corpo)
        assert r.status_code == 201, r.text
        j = r.json()
        assert j["mrr"] == 7500.5 and j["complexidade"] == "Alta" and j["cnpj"] == "12345678000190"
        assert j["data_inicio"] == "2026-08-01" and j["proximo_contato"] == "2026-10-15" and j["responsavel"] == "Wallison Rocha"
        assert c.post("/api/contas", json={"nome": "LOJA NOVA Ltda", "nivel": "ME", "mrr": 1}).status_code == 422
        r = c.post("/api/contas", json={"nome": "X", "nivel": "Ouro", "mrr": -1, "cnpj": "123", "contato_email": "a@", "complexidade": "Enorme", "data_inicio": "31/31/2026"})
        assert r.status_code == 422 and len(r.json()["detail"]["erros"]) == 6
        r = c.post("/api/contas", json={"nome": "Grupo Linhares - Financeiro", "nivel": "Legado", "mrr": 6000, "segmento": "a"})
        assert r.status_code == 201 and any("contrato" in a for a in r.json()["avisos"]) and any("teto" in a for a in r.json()["avisos"])
        assert [x["nome"] for x in c.get("/api/contas", params={"complexidade": "Alta"}).json()] == ["Loja Nova"]
        assert [x["nome"] for x in c.get("/api/contas", params={"segmento": "varejo"}).json()] == ["Loja Nova"]
        assert c.get("/api/contas", params={"q": "protheus"}).json()[0]["nome"] == "Loja Nova"
        cid = j["id"]
        r = c.patch(f"/api/contas/{cid}", json={"complexidade": "Média", "contato_nome": "Bia"})
        assert r.json()["complexidade"] == "Média" and r.json()["contato_nome"] == "Bia"
        h = c.get("/api/historico").json()
        assert any(x["campo"] == "complexidade" and x["valor_novo"] == "Média" for x in h)


def test_cadastro_projeto_e_edicao():
    with TestClient(app) as c0:
        c = entrar(c0)
        assert c.post("/api/projetos", json={"conta": "Inexistente", "nome": "P", "tipo": "Melhoria"}).status_code == 422
        conta = c.get("/api/contas", params={"q": "Loja Nova"}).json()[0]
        r = c.post("/api/projetos", json={"conta_id": conta["id"], "nome": "Integração ERP", "tipo": "integracao", "bloqueio_dono": "Aguardando cliente"})
        assert r.status_code == 422 and "motivo" in r.json()["detail"]["erros"][0]
        prazo = (date.today() + timedelta(days=1)).isoformat()
        r = c.post("/api/projetos", json={"conta_id": conta["id"], "nome": "Integração ERP", "tipo": "integracao", "prazo": prazo})
        assert r.status_code == 201, r.text
        p = r.json()
        assert p["farol"]["cor"] == "Y" and p["prioridade"]["urgencia"] == 3
        assert c.post("/api/projetos", json={"conta_id": conta["id"], "nome": "integração erp", "tipo": "Melhoria"}).status_code == 422
        assert c.patch(f"/api/projetos/{p['id']}", json={"critico": True, "situacao": "Parado"}).json()["farol"]["cor"] == "R"
        h = c.get(f"/api/projetos/{p['id']}").json()["historico"]
        assert any(x["campo"] == "farol" and x["valor_anterior"] == "Y" and x["valor_novo"] == "R" for x in h)
        r = c.patch(f"/api/projetos/{p['id']}", json={"prazo": (date.today() - timedelta(days=9)).isoformat(), "critico": False})
        assert r.json()["farol"]["cor"] == "R" and "Atraso de 9" in r.json()["farol"]["motivo"]


def test_multiusuario_isolamento():
    with TestClient(app) as c0:
        adm = entrar(c0)
        assert adm.post("/api/usuarios", json={"email": "bia@suri.ai", "nome": "Bia", "senha": "curta"}).status_code == 422
        r = adm.post("/api/usuarios", json={"email": "Bia@suri.ai", "nome": "Bia AM", "senha": "provisoria123"})
        assert r.status_code == 201 and r.json()["papel"] == "am"
        assert adm.post("/api/usuarios", json={"email": "bia@suri.ai", "nome": "x", "senha": "provisoria123"}).status_code == 422
        uid = r.json()["id"]
        with TestClient(app) as b:
            entrar(b, "bia@suri.ai", "provisoria123")
            assert b.get("/api/contas").json() == [] and b.get("/api/carteira/farol").json()["resumo"]["projetos"] == 0
            assert b.get("/api/usuarios").status_code == 403
            alheia = adm.get("/api/contas", params={"q": "Carajás"}).json()[0]["id"]
            assert b.get(f"/api/contas/{alheia}").status_code == 404 and b.patch(f"/api/contas/{alheia}", json={"nota": "x"}).status_code == 404
            assert b.post("/api/projetos", json={"conta_id": alheia, "nome": "Invasão", "tipo": "Melhoria"}).status_code == 422
            pid = adm.get("/api/projetos", params={"q": "Carajás"}).json()[0]["id"]
            assert b.get(f"/api/projetos/{pid}").status_code == 404 and b.patch(f"/api/projetos/{pid}", json={"critico": True}).status_code == 404
            r = b.post("/api/contas", json={"nome": "Cliente da Bia", "nivel": "Legado", "mrr": 1000, "segmento": "x", "complexidade": "Baixa"})
            assert r.status_code == 201 and r.json()["responsavel"] == "Bia AM"
            assert b.post("/api/contas", json={"nome": "Carajás", "nivel": "ME", "mrr": 1}).status_code == 422   # unicidade global
            assert [x["nome"] for x in b.get("/api/contas").json()] == ["Cliente da Bia"]
            assert all(h["rotulo"].startswith("Cliente da Bia") for h in b.get("/api/historico").json())
            assert b.post("/api/auth/senha", json={"atual": "errada", "nova": "novaSenha123"}).status_code == 422
            assert b.post("/api/auth/senha", json={"atual": "provisoria123", "nova": "novaSenha123"}).status_code == 200
        assert any(x["nome"] == "Cliente da Bia" for x in adm.get("/api/contas").json())                       # admin vê tudo
        assert [x["nome"] for x in adm.get("/api/contas", params={"responsavel_id": uid}).json()] == ["Cliente da Bia"]
        assert adm.patch(f"/api/usuarios/{uid}", json={"ativo": False}).status_code == 200
        with TestClient(app) as b2:
            assert b2.post("/api/auth/login", json={"email": "bia@suri.ai", "senha": "novaSenha123"}).status_code == 401
        me = adm.get("/api/auth/eu").json()["id"]
        assert adm.patch(f"/api/usuarios/{me}", json={"ativo": False}).status_code == 422


def test_importacao_csv_xlsx_json():
    with TestClient(app) as c0:
        c = entrar(c0)
        csvt = "nome;nível;MRR;segmento;complexidade;e-mail\nImp Um;LE;10.000,00;Teste;Alta;a@b.com\nImp Um;LE;1;x;;\nImp Dois;Platina;5;y;;\n".encode()
        r = c.post("/api/importacoes", params={"dry_run": True}, files={"arquivo": ("c.csv", csvt)}).json()
        assert r["validos"] == 1 and r["com_erro"] == 2 and r["gravados"] == 0
        assert not c.get("/api/contas", params={"q": "Imp Um"}).json()
        wb = Workbook(); a = wb.active; a.title = "Contas"
        a.append(["Nome", "Nível", "MRR", "Segmento", "Complexidade"]); a.append(["Imp Xlsx", "ME", 12000, "Teste", "Média"])
        b = wb.create_sheet("Projetos")
        b.append(["Conta", "Projeto", "Tipo", "Prazo", "Bloqueio", "Motivo do bloqueio"])
        b.append(["Imp Xlsx", "Go-live", "Implantação", date.today() + timedelta(days=3), "Aguardando engenharia", "API"])
        b.append(["Fantasma", "Go-live", "Implantação", None, None, None])
        buf = io.BytesIO(); wb.save(buf)
        r = c.post("/api/importacoes", files={"arquivo": ("x.xlsx", buf.getvalue())}).json()
        assert r["gravados"] == 2 and r["com_erro"] == 1
        assert c.get("/api/contas", params={"complexidade": "Média"}).json()[0]["nome"] == "Imp Xlsx"
        assert c.get("/api/projetos", params={"q": "Imp Xlsx"}).json()[0]["farol"]["cor"] == "Y"
        j = b'{"contas":[{"nome":"Imp Json","nivel":"Legado","mrr":100,"segmento":"s"}],"projetos":[]}'
        assert c.post("/api/importacoes", files={"arquivo": ("j.json", j)}).json()["gravados"] == 1
        assert c.post("/api/importacoes", files={"arquivo": ("a.txt", b"x")}).status_code == 400
        assert c.post("/api/importacoes", files={"arquivo": ("x.xlsx", b"lixo")}).status_code == 400


def test_webhook_com_token_de_servico(monkeypatch):
    with TestClient(app) as c:
        monkeypatch.setenv("API_TOKEN", "segredo-servico")
        c.headers["Authorization"] = "Bearer segredo-servico"
        r = c.post("/api/webhooks/projetos", json={"conta": "carajas", "projeto": "go-live", "situacao": "Em homologação", "prazo": "30/12/2099"})
        assert r.status_code == 200 and r.json()["acao"] == "atualizado"
        assert c.post("/api/webhooks/projetos", json={"conta": "Doterra", "projeto": "Novo evento", "tipo": "Melhoria"}).json()["acao"] == "criado"
        assert c.post("/api/webhooks/projetos", json={"conta": "Nope", "projeto": "x"}).status_code == 422
        c.headers["Authorization"] = "Bearer outro"
        assert c.post("/api/webhooks/projetos", json={"conta": "Doterra", "projeto": "x"}).status_code == 401


def test_limite_de_tentativas_de_login():
    with TestClient(app) as c:
        m.FALHAS.clear()
        for _ in range(5):
            assert c.post("/api/auth/login", json={"email": "alvo@x.com", "senha": "x"}).status_code == 401
        assert c.post("/api/auth/login", json={"email": "alvo@x.com", "senha": "x"}).status_code == 429
        m.FALHAS.clear()
