"""Motor de oportunidades: decide o que é promoção de verdade e se vale usar milhas."""
from __future__ import annotations

from statistics import median

from .config import Config
from .db import Historico
from .providers.base import link_google

NIVEIS = {
    "erro": "Possível erro tarifário",
    "otima": "Ótima",
    "boa": "Boa",
    "normal": "Preço normal",
}


def classificar(preco: float, regiao: str, historico: list[tuple[str, float]], cfg: Config) -> dict:
    """Compara o preço com o histórico da própria rota (ou com a referência inicial)."""
    regras = cfg.oportunidade
    if len(historico) >= regras["min_dias_historico"]:
        normal = median(p for _, p in historico)
        desconto = round(1 - preco / normal, 4) if normal else 0.0
        if desconto >= regras["desconto_erro"]:
            nivel = "erro"
        elif desconto >= regras["desconto_otimo"]:
            nivel = "otima"
        elif desconto >= regras["desconto_bom"]:
            nivel = "boa"
        else:
            nivel = "normal"
        return {"nivel": nivel, "base": "historico", "preco_normal": round(normal, 2),
                "desconto": round(desconto, 4), "dias_historico": len(historico)}

    ref = cfg.referencia_inicial.get(regiao, {})
    nivel = "normal"
    if ref and preco <= ref["otimo"]:
        nivel = "otima"
    elif ref and preco <= ref["bom"]:
        nivel = "boa"
    normal = ref.get("bom")
    desconto = (1 - preco / normal) if normal else 0.0
    return {"nivel": nivel, "base": "referencia", "preco_normal": normal,
            "desconto": round(desconto, 4), "dias_historico": len(historico)}


def avaliar_milhas(oferta: dict, cfg: Config) -> dict:
    """Quanto vale a pena pagar em milhas por esta passagem e o que as tabelas fixas cobram."""
    m = cfg.milhas
    regiao = oferta["regiao"]
    trechos = 2 if oferta["tipo"] == "ida_volta" else 1
    taxas = m["taxas_estimadas"].get(regiao, 0)
    liquido = max(oferta["preco"] - taxas, 0)
    minimo = m["valor_minimo_milheiro"]

    teto = int(liquido / minimo * 1000) if minimo else 0
    comparacoes = []
    for t in cfg.tabelas_milhas:
        if t.get("regiao") != regiao:
            continue
        dests = t.get("destinos", "todos")
        if dests != "todos" and oferta["destino"] not in dests:
            continue
        if not t.get("economica"):
            continue
        milhas = t["economica"] * trechos
        valor = round(liquido / milhas * 1000, 2) if milhas else 0
        comparacoes.append({
            "programa": t["programa"],
            "voa_com": t.get("voa_com", ""),
            "milhas": milhas,
            "valor_milheiro": valor,
            "vale": valor >= minimo,
            "executiva": (t["executiva"] * trechos) if t.get("executiva") else None,
            "observacao": t.get("observacao", ""),
            "fonte": t.get("fonte", ""),
        })
    comparacoes.sort(key=lambda c: -c["valor_milheiro"])
    melhor = comparacoes[0] if comparacoes and comparacoes[0]["vale"] else None
    if melhor:
        veredito = f"Use milhas: {melhor['programa']} ({melhor['milhas']:,} milhas)".replace(",", ".")
    elif comparacoes:
        veredito = "Pague em reais (as tabelas fixas rendem pouco neste preço)"
    else:
        veredito = f"Só emita com milhas se custar até {teto:,} milhas + taxas".replace(",", ".")
    return {
        "taxas_estimadas": taxas,
        "teto_milhas": teto,
        "custo_com_meu_milheiro": round(teto / 1000 * m["meu_custo_milheiro"], 2),
        "comparacoes": comparacoes,
        "veredito": veredito,
        "usar_milhas": bool(melhor),
    }


def analisar(hist: Historico, cfg: Config) -> dict:
    """Gera o resultado completo da última coleta, pronto para o painel."""
    coleta = hist.ultima_coleta()
    if not coleta:
        return {"coleta": None, "ofertas": [], "series": {}}
    dia, fonte = coleta["dia"], coleta["fonte"]
    janela = cfg.oportunidade["janela_historico_dias"]

    # Melhor oferta por rota e mês de ida (evita repetir a mesma rota 30 vezes)
    melhores: dict[tuple, dict] = {}
    for o in hist.ofertas_da_coleta(coleta["id"]):
        k = (o["chave_rota"], o["ida"][:7])
        if k not in melhores or o["preco"] < melhores[k]["preco"]:
            melhores[k] = o

    min_dias = cfg.oportunidade["min_dias_historico"]
    cache_rota: dict[str, list] = {}
    resultado = []
    for o in melhores.values():
        rota, mes = o["chave_rota"], o["ida"][:7]
        # 1º: compara com o mesmo mês de viagem (dezembro com dezembro)
        historico = hist.minimos_diarios(rota, dia, janela, fonte, mes_ida=mes)
        comparacao = "mesmo mês de viagem"
        if len(historico) < min_dias:
            # 2º: sem histórico do mês, usa a rota inteira
            if rota not in cache_rota:
                cache_rota[rota] = hist.minimos_diarios(rota, dia, janela, fonte)
            historico, comparacao = cache_rota[rota], "todos os meses da rota"
        c = classificar(o["preco"], o["regiao"], historico, cfg)
        c["comparacao"] = comparacao if c["base"] == "historico" else None
        minimo = hist.minimo_historico(rota, dia, fonte)
        o = dict(o)
        o.update(c)
        o["menor_ja_visto"] = bool(minimo is not None and o["preco"] < minimo and len(historico) >= 3)
        o["milhas"] = avaliar_milhas(o, cfg)
        o["nome_origem"] = cfg.nome_origem(o["origem"])
        o["nome_destino"] = cfg.nome_destino(o["destino"])
        o["nome_regiao"] = cfg.regioes[o["regiao"]]["nome"]
        o["link_google"] = link_google(o["origem"], o["aeroporto_destino"] or o["destino"], o["ida"], o["volta"])
        resultado.append(o)

    ordem = {"erro": 0, "otima": 1, "boa": 2, "normal": 3}
    resultado.sort(key=lambda x: (ordem[x["nivel"]], -x["desconto"], x["preco"]))
    return {
        "coleta": dict(coleta),
        "ofertas": resultado,
        "series": hist.serie_completa(fonte, dia, janela),
    }
