"""Carga inicial com os dados informados pelo AM em 28/09/2026 (data de atualização = dia da carga). Só roda com o banco vazio."""
from datetime import date
from sqlalchemy import select, func
from .db import Conta, Projeto
from .rules import norm

CONTAS = [  # nome, nivel, mrr, segmento, nota, churn
 ("NEWLAND","LE",70490.29,"Concessionária de carros","Usa muito para atendimento; pede muita melhoria de métricas, atendimentos e integrações",0),
 ("Grupo Linhares","LE",47248.55,None,"Uso forte em atendimento; contratos de atendimento e Backoffice em plataformas diferentes (R$ 47.236,43 + R$ 12,12)",0),
 ("CASA RENA","LE",34320.00,"Supermercado",None,0),
 ("ADITEK","LE",25193.03,"Produtos ortodônticos","Referência mundial em produtos ortodônticos",0),
 ("Farmácia Santa Catarina","ME",13549.68,"Farmácia",None,0),
 ("Carajás","ME",11820.90,"Varejo de material de construção, eletrodomésticos e itens para casa","Grande varejista",0),
 ("Drogamax 5","ME",11803.02,"Farmácias",None,0),
 ("Doterra","ME",10696.40,"Óleos essenciais","Empresa internacional muito grande",0),
 ("Café Orfeu","Growth",9365.55,"Café",None,0),
 ("Casas Pedro","Growth",8580.00,"Alimentícios e temperos",None,0),
 ("Central Ar","Growth",8018.12,None,"Muitas integrações; empresa muito grande",0),
 ("Ikesaki","Growth",7920.00,"Cosméticos",None,0),
 ("Barra Oeste","Growth",6782.49,"Supermercado",None,0),
 ("Bionnovation","Growth",6495.87,None,"Produtos desenvolvidos em colaboração com profissionais e para profissionais",0),
 ("Omni Pet","Legado",3696.00,"Produtos pet",None,0),
 ("Porto Franco","Legado",3432.00,"Indústria têxtil",None,0),
 ("Cricaré","Legado",3432.00,"Supermercado",None,0),
 ("Gerozan","Legado",2772.00,"Produtos pet",None,0),
 ("Gnatus","Legado",2574.00,"Produtos médicos e odontológicos",None,0),
 ("Punto Farma","Legado",2145.00,"Farmácias","Maior rede de farmácias do Paraguai",0),
 ("Freios Farj","Legado",1320.00,"Peças para freios pneumáticos e embreagens de veículos pesados",None,0),
 ("Moniari","Legado",1287.00,"Supermercado",None,0),
 ("Hiperideal","Legado",965.25,"Supermercado",None,0),
 ("Mart Minas","LE",99000.00,None,"Novo: em implantação",0),
 ("Paulista Supermercado","Legado",5940.00,None,"Novo: em implantação; MRR acima do teto de Legado, revisar nível",0),
 ("Hoje Cosmetics","Legado",4290.00,"Cosméticos","Churn (Grupo J Cruz)",1),
]
# conta, nome, tipo, situacao, critico, (bloqueio_dono, motivo)
PROJ = [
 ("CASA RENA","Implantação","Implantação","Finalizando a implantação",0,None),
 ("ADITEK","Implantação multi-times","Implantação","Lado Suri adiantado; desalinhamento comercial e outros times pendentes",0,("Aguardando terceiro","Dependência dos demais times do projeto")),
 ("Carajás","Go-live","Implantação","Próximo do go-live",0,("Aguardando engenharia","Melhoria Suri em desenvolvimento")),
 ("Doterra","Projeto do cliente","Acompanhamento","Acompanhando projeto do cliente; sem pendência Suri",0,None),
 ("Casas Pedro","Restrições de WhatsApp","Risco","Restrições de WhatsApp dificultam a operação e geraram perda financeira ao cliente",1,None),
 ("Central Ar","Integrações","Integração","Acompanhar as diversas integrações",0,None),
 ("Barra Oeste","Integração de produtos","Integração","Operação em acompanhamento",0,("Outro","Integração sem as imagens dos produtos")),
 ("Bionnovation","Operação pós-ERP","Acompanhamento","Integração de ERP finalizada; acompanhar operação",0,None),
 ("Omni Pet","Preço Meta","Risco","Crítico pela alteração de precificação da Meta",1,None),
 ("Porto Franco","Integração ERP","Integração","Acompanhando integração com ERP",0,None),
 ("Gerozan","Preço Meta","Risco","Crítico pela alteração de precificação da Meta",1,None),
 ("Mart Minas","Implantação inicial","Implantação","Projeto inicial em implantação",0,None),
 ("NEWLAND","Melhorias de plataforma","Melhoria","Solicitações e entregas de melhoria (métricas, atendimento, integrações)",0,None),
 ("Paulista Supermercado","Implantação","Implantação","Status não informado",0,None),
]


def seed(db, dono_id=None):
    if db.scalar(select(func.count()).select_from(Conta)):
        return False
    ids = {}
    for n, nv, mrr, seg, nota, ch in CONTAS:
        c = Conta(nome=n, nome_norm=norm(n), nivel=nv, mrr=mrr, segmento=seg, nota=nota, churn=bool(ch), responsavel_id=dono_id)
        db.add(c); db.flush(); ids[n] = c.id
    for c, n, t, sit, crit, bl in PROJ:
        db.add(Projeto(conta_id=ids[c], nome=n, nome_norm=norm(n), tipo=t, situacao=sit, critico=bool(crit),
                       bloqueio_dono=bl[0] if bl else None, bloqueio_motivo=bl[1] if bl else None,
                       ultima_atualizacao=date.today()))
    db.commit()
    return True
