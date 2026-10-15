"""Linha de comando do Radar de Passagens.

    python -m radar.main coletar     # busca preços e grava no histórico
    python -m radar.main painel      # gera site/index.html com as oportunidades
    python -m radar.main tudo        # coletar + painel (o que o GitHub Actions roda)
    python -m radar.main demo        # simula 30 dias com preços fictícios (sem token)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from . import config as cfgmod
from .analise import analisar
from .db import Historico
from .painel import gerar_painel
from .providers import DemoProvider, TravelpayoutsProvider

log = logging.getLogger("radar")
RAIZ = cfgmod.RAIZ
DB_REAL = RAIZ / "data" / "historico.db"
DB_DEMO = RAIZ / "data" / "demo.db"
SITE = RAIZ / "site" / "index.html"


def meses(qtd: int, hoje: date | None = None) -> list[str]:
    hoje = hoje or date.today()
    out, ano, mes = [], hoje.year, hoje.month
    for _ in range(qtd):
        out.append(f"{ano:04d}-{mes:02d}")
        mes += 1
        if mes > 12:
            mes, ano = 1, ano + 1
    return out


def coletar(cfg, hist: Historico, provider, dia: date | None = None) -> int:
    coleta_id = hist.nova_coleta(provider.nome, dia)
    todas = []
    rotas = cfg.rotas()
    lista_meses = meses(cfg.meses_a_frente, dia)
    total = len(rotas) * len(lista_meses)
    feito = 0
    for rota in rotas:
        for mes in lista_meses:
            todas.extend(provider.buscar(rota, mes))
            feito += 1
            if feito % 100 == 0:
                log.info("%s/%s consultas, %s ofertas", feito, total, len(todas))
    hist.salvar(coleta_id, todas, provider.chamadas, provider.falhas)
    log.info("Coleta %s: %s ofertas, %s chamadas, %s falhas", coleta_id, len(todas), provider.chamadas, provider.falhas)
    return len(todas)


def cmd_coletar(cfg) -> int:
    if not os.environ.get("TRAVELPAYOUTS_TOKEN"):
        log.error("TRAVELPAYOUTS_TOKEN não definido. Veja o README (passo 2). Para testar sem token: demo")
        return 2
    hist = Historico(DB_REAL)
    n = coletar(cfg, hist, TravelpayoutsProvider())
    hist.limpar_antigos()
    hist.fechar()
    if n == 0:
        log.error("Nenhuma oferta coletada — confira o token e os logs acima.")
        return 1
    return 0


def cmd_painel(cfg, db: Path, demo: bool = False) -> int:
    hist = Historico(db)
    dados = analisar(hist, cfg)
    hist.con.close()
    gerar_painel(dados, cfg, SITE, demo=demo)
    ops = sum(1 for o in dados["ofertas"] if o["nivel"] != "normal")
    log.info("Painel gerado em %s — %s oportunidades em %s ofertas", SITE, ops, len(dados["ofertas"]))
    return 0


def cmd_demo(cfg, dias: int = 30) -> int:
    if DB_DEMO.exists():
        DB_DEMO.unlink()
    hist = Historico(DB_DEMO)
    hoje = date.today()
    for i in range(dias, -1, -1):
        dia = hoje - timedelta(days=i)
        coletar(cfg, hist, DemoProvider(dia), dia)
    hist.fechar()
    return cmd_painel(cfg, DB_DEMO, demo=True)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Radar de Passagens")
    p.add_argument("comando", choices=["coletar", "painel", "tudo", "demo"])
    p.add_argument("--dias", type=int, default=30, help="dias simulados no modo demo")
    a = p.parse_args(argv)
    cfg = cfgmod.carregar()
    if a.comando == "coletar":
        return cmd_coletar(cfg)
    if a.comando == "painel":
        return cmd_painel(cfg, DB_REAL)
    if a.comando == "tudo":
        rc = cmd_coletar(cfg)
        if rc not in (0,):
            # Mesmo com falha na coleta, publica o painel com o último histórico válido
            if DB_REAL.exists():
                cmd_painel(cfg, DB_REAL)
            return rc
        return cmd_painel(cfg, DB_REAL)
    return cmd_demo(cfg, a.dias)


if __name__ == "__main__":
    sys.exit(main())
