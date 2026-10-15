"""Gera o painel web (site/index.html) a partir da análise."""
from __future__ import annotations

import json
from pathlib import Path

from .config import Config

TEMPLATE = Path(__file__).parent / "templates" / "painel.html"
CAMPOS = [
    "chave_rota", "origem", "destino", "aeroporto_destino", "regiao", "tipo", "preco", "cia",
    "ida", "volta", "escalas", "link_fonte", "link_google", "nivel", "base", "preco_normal",
    "desconto", "dias_historico", "comparacao", "menor_ja_visto", "milhas", "nome_origem", "nome_destino",
]


def gerar_painel(dados: dict, cfg: Config, destino: Path, demo: bool = False) -> Path:
    ofertas = [{k: o.get(k) for k in CAMPOS} for o in dados["ofertas"]]
    programas = {}
    for o in ofertas:
        o["serie"] = f'{o["chave_rota"]}|{o["ida"][:7]}'
        m = dict(o["milhas"])
        comps = []
        for c in m["comparacoes"]:
            programas[c["programa"]] = c["observacao"]  # nota guardada uma vez só
            comps.append({k: c[k] for k in ("programa", "milhas", "valor_milheiro", "vale")})
        m["comparacoes"] = comps
        o["milhas"] = m
    rotas = {o["serie"] for o in ofertas}
    payload = {
        "demo": demo,
        "coleta": dados["coleta"],
        "ofertas": ofertas,
        # Só os preços (inteiros), em ordem de dia, para o arquivo ficar leve no celular
        "series": {k: [round(p) for _, p in v] for k, v in dados["series"].items() if k in rotas},
        "programas": programas,
        "regioes": {k: v["nome"] for k, v in cfg.regioes.items()},
        "origens": cfg.origens,
        "valor_minimo_milheiro": cfg.milhas["valor_minimo_milheiro"],
    }
    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DADOS__", js)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    return destino
