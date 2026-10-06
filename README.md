# Farol da Carteira — backend + painel

FastAPI + SQLAlchemy. Banco: SQLite por padrão (arquivo `farol.db`) ou PostgreSQL via `DATABASE_URL`.
O painel (`public/index.html`) é servido pelo próprio backend em `/` e usa a API.

## Rodar local
```
pip install -r requirements.txt
API_TOKEN=troque-este-token uvicorn app.main:app --port 8000
```
Abra http://localhost:8000 (painel) ou http://localhost:8000/docs (documentação interativa da API).
Sem `API_TOKEN` a API fica aberta (só para uso local). Com token, o painel pede o token na primeira abertura.

## Variáveis de ambiente
| Variável | Função |
|---|---|
| `DATABASE_URL` | ex.: `postgresql://user:senha@host:5432/farol`. Padrão: SQLite local |
| `API_TOKEN` | exige `Authorization: Bearer <token>` em toda a API |
| `SEED` | `0` desliga a carga inicial (por padrão, carrega a carteira informada no primeiro start com banco vazio) |

## Publicar no Vercel
1. Suba esta pasta para um repositório no GitHub e importe o repositório no Vercel (detecta FastAPI sozinho; entrada: `main.py`).
2. Crie um PostgreSQL (Neon ou Supabase, pelo Marketplace do Vercel ou direto) e defina em *Settings > Environment Variables*:
   `DATABASE_URL` (o Marketplace já cria essa variável) e `API_TOKEN`.
3. Faça o deploy. No primeiro acesso as tabelas e a carga inicial são criadas sozinhas.
- No Vercel o disco não persiste: sem `DATABASE_URL` a API responde 503 com uma mensagem explicando o que falta (em vez de perder dados em silêncio).
- O painel fica em `public/` (servido pelo CDN do Vercel); a API roda como função serverless, sem pool de conexões.
- Confira se o plano do Vercel e a política interna permitem hospedar dados de clientes.

## Publicar em servidor próprio (Docker)
Precisa de um servidor. Com o `Dockerfile`, serve em Render, Railway, Fly.io ou qualquer VM:
defina `DATABASE_URL` (Postgres gerenciado) e `API_TOKEN`. Em SQLite, use disco persistente.

## API (todas em /api, JSON)
| Método | Rota | Função |
|---|---|---|
| GET/POST | /contas | listar (`q`, `nivel`), cadastrar |
| GET/PATCH | /contas/{id} | detalhe com projetos, editar (inclui `churn`) |
| GET/POST | /projetos | listar (`conta_id`, `tipo`, `farol`, `q`, `bloqueado`), cadastrar |
| GET/PATCH | /projetos/{id} | detalhe com histórico, editar |
| GET | /carteira/farol | resumo, contas e projetos com farol, prioridade e motivos |
| GET | /historico | auditoria (data, usuário, campo, antes, depois) |
| POST | /importacoes?dry_run=true | valida `.xlsx`, `.csv` ou `.json` sem gravar; sem `dry_run` grava os registros válidos |
| POST | /webhooks/projetos | cria ou atualiza projeto por `conta` + `projeto` (CRM, service desk) |

Erros de regra voltam como HTTP 422 com `{"detail":{"erros":[...],"avisos":[...]}}`. O header opcional `X-Usuario` identifica quem alterou no histórico.

## Regras (arquivo `app/rules.py`)
Cadastro, farol e prioridade ficam só no servidor. Prioridade = impacto (nível da conta ± ajuste) + urgência (prazo) + risco.
Diferença em relação ao painel anterior: prazo vencido conta como risco alto.
Limites do farol (atraso > 5 dias = vermelho; sem atualização > 7 dias = cinza etc.) são constantes em `farol()`.

## Importação
`.xlsx` (uma aba por tipo), `.csv` (`,` `;` ou tab; UTF-8 ou Latin-1) ou `.json` (`{"contas":[],"projetos":[]}`).
Contas são processadas antes dos projetos, então um arquivo pode trazer os dois. `.xls` antigo: salve como `.xlsx`.

## Testes
`pip install pytest httpx && pytest` (também contra PostgreSQL: `DATABASE_URL=postgresql://... pytest`; 6 testes: carga, regras de cadastro, farol/histórico, importação xlsx/csv/json, webhook, token).
