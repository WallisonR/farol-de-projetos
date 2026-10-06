import io, os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.pop("API_TOKEN", None)
from datetime import date, timedelta
from fastapi.testclient import TestClient
from openpyxl import Workbook
from app.main import app

def cli():
    return TestClient(app)

def test_seed_e_carteira():
    with cli() as c:
        d = c.get("/api/carteira/farol").json()
        assert d["resumo"]["contas_ativas"] == 25          # 26 seed - 1 churn
        assert d["resumo"]["projetos"] == 14
        cores = {p["conta"] + "/" + p["nome"]: p["farol"]["cor"] for p in d["projetos"]}
        assert cores["Omni Pet/Preço Meta"] == "R"
        assert cores["ADITEK/Implantação multi-times"] == "Y"
        assert cores["Bionnovation/Operação pós-ERP"] == "G"
        assert cores["CASA RENA/Implantação"] == "C"       # sem prazo: nunca verde
        assert all(p["farol"]["motivo"] for p in d["projetos"])
        assert d["projetos"][0]["prioridade"]["fatores"]

def test_cadastro_conta_regras():
    with cli() as c:
        r = c.post("/api/contas", json={"nome": "Loja Nova", "nivel": "Growth", "mrr": "7.500,50", "segmento": "Varejo"})
        assert r.status_code == 201 and r.json()["mrr"] == 7500.5
        assert c.post("/api/contas", json={"nome": "LOJA NOVA Ltda", "nivel": "ME", "mrr": 1}).status_code == 422
        r = c.post("/api/contas", json={"nome": "X", "nivel": "Ouro", "mrr": -1})
        assert r.status_code == 422 and len(r.json()["detail"]["erros"]) == 2
        r = c.post("/api/contas", json={"nome": "Grupo Linhares - Financeiro", "nivel": "Legado", "mrr": 6000, "segmento": "a"})
        assert r.status_code == 201
        assert any("contrato" in a for a in r.json()["avisos"]) and any("teto" in a for a in r.json()["avisos"])

def test_cadastro_projeto_e_edicao():
    with cli() as c:
        assert c.post("/api/projetos", json={"conta": "Inexistente", "nome": "P", "tipo": "Melhoria"}).status_code == 422
        conta = c.get("/api/contas", params={"q": "Loja Nova"}).json()[0]
        r = c.post("/api/projetos", json={"conta_id": conta["id"], "nome": "Integração ERP", "tipo": "integracao",
                                            "bloqueio_dono": "Aguardando cliente"})
        assert r.status_code == 422 and "motivo" in r.json()["detail"]["erros"][0]
        prazo = (date.today() + timedelta(days=1)).isoformat()
        r = c.post("/api/projetos", json={"conta_id": conta["id"], "nome": "Integração ERP", "tipo": "integracao", "prazo": prazo})
        assert r.status_code == 201, r.text
        p = r.json()
        assert p["farol"]["cor"] == "Y" and p["prioridade"]["urgencia"] == 3
        assert c.post("/api/projetos", json={"conta_id": conta["id"], "nome": "integração erp", "tipo": "Melhoria"}).status_code == 422
        r = c.patch(f"/api/projetos/{p['id']}", json={"critico": True, "situacao": "Cliente parado"})
        assert r.json()["farol"]["cor"] == "R"
        h = c.get(f"/api/projetos/{p['id']}").json()["historico"]
        assert any(x["campo"] == "farol" and x["valor_anterior"] == "Y" and x["valor_novo"] == "R" for x in h)
        r = c.patch(f"/api/projetos/{p['id']}", json={"prazo": (date.today() - timedelta(days=9)).isoformat(), "critico": False})
        assert r.json()["farol"]["cor"] == "R" and "Atraso de 9" in r.json()["farol"]["motivo"]

def test_importacao_csv_xlsx_json():
    with cli() as c:
        csvt = "nome;nível;MRR;segmento\nImp Um;LE;10.000,00;Teste\nImp Um;LE;1;x\nImp Dois;Platina;5;y\n".encode()
        r = c.post("/api/importacoes", params={"dry_run": True}, files={"arquivo": ("c.csv", csvt)}).json()
        assert r["validos"] == 1 and r["com_erro"] == 2 and r["gravados"] == 0
        assert not [x for x in c.get("/api/contas", params={"q": "Imp Um"}).json()]      # dry_run não grava
        wb = Workbook(); a = wb.active; a.title = "Contas"
        a.append(["Nome", "Nível", "MRR", "Segmento"]); a.append(["Imp Xlsx", "ME", 12000, "Teste"])
        b = wb.create_sheet("Projetos")
        b.append(["Conta", "Projeto", "Tipo", "Prazo", "Bloqueio", "Motivo do bloqueio"])
        b.append(["Imp Xlsx", "Go-live", "Implantação", date.today() + timedelta(days=3), "Aguardando engenharia", "API"])
        b.append(["Fantasma", "Go-live", "Implantação", None, None, None])
        buf = io.BytesIO(); wb.save(buf)
        r = c.post("/api/importacoes", files={"arquivo": ("x.xlsx", buf.getvalue())}).json()
        assert r["gravados"] == 2 and r["com_erro"] == 1   # conta + projeto na mesma planilha; fantasma rejeitado
        ps = c.get("/api/projetos", params={"q": "Imp Xlsx"}).json()
        assert ps[0]["farol"]["cor"] == "Y" and ps[0]["bloqueio_dono"] == "Aguardando engenharia"
        j = b'{"contas":[{"nome":"Imp Json","nivel":"Legado","mrr":100,"segmento":"s"}],"projetos":[]}'
        assert c.post("/api/importacoes", files={"arquivo": ("j.json", j)}).json()["gravados"] == 1
        assert c.post("/api/importacoes", files={"arquivo": ("a.txt", b"x")}).status_code == 400
        assert c.post("/api/importacoes", files={"arquivo": ("x.xlsx", b"lixo")}).status_code == 400

def test_webhook_e_auth(monkeypatch):
    with cli() as c:
        r = c.post("/api/webhooks/projetos", json={"conta": "carajas", "projeto": "go-live", "situacao": "Em homologação", "prazo": "30/12/2099"})
        assert r.status_code == 200 and r.json()["acao"] == "atualizado"
        r = c.post("/api/webhooks/projetos", json={"conta": "Doterra", "projeto": "Novo evento", "tipo": "Melhoria"})
        assert r.json()["acao"] == "criado"
        assert c.post("/api/webhooks/projetos", json={"conta": "Nope", "projeto": "x"}).status_code == 422
        monkeypatch.setenv("API_TOKEN", "segredo")
        assert c.get("/api/contas").status_code == 401
        assert c.get("/api/contas", headers={"Authorization": "Bearer segredo"}).status_code == 200
        assert c.get("/").status_code == 200

def test_churn_fora_da_carteira():
    with cli() as c:
        hoje = [x for x in c.get("/api/contas").json() if x["nome"] == "Hoje Cosmetics"][0]
        assert hoje["churn"] is True
        assert c.patch(f"/api/contas/{hoje['id']}", json={"nivel": "ME"}).status_code == 200
