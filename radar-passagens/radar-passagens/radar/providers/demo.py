"""Fonte de DEMONSTRAÇÃO: preços fictícios, só para testar o sistema sem token.

Nunca é usada quando existe TRAVELPAYOUTS_TOKEN. As ofertas saem marcadas
como fonte "demo" e o painel exibe um aviso em destaque.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

from ..config import Rota
from .base import Oferta

BASE = {"europa": 4600, "eua": 4000, "america_sul": 2000, "nacional": 480}
CIAS = {
    "europa": ["TP", "IB", "AF", "KL", "LA", "UX"],
    "eua": ["LA", "AA", "DL", "UA", "AD"],
    "america_sul": ["LA", "G3", "AR", "H2", "JA"],
    "nacional": ["LA", "G3", "AD"],
}
# Distância relativa por origem (aeroportos do interior costumam ser mais caros)
FATOR_ORIGEM = {"GRU": 1.0, "CGH": 1.03, "VCP": 1.02, "RAO": 1.12, "SJP": 1.15}


def _semente(*partes) -> int:
    return int(hashlib.sha1("|".join(map(str, partes)).encode()).hexdigest()[:12], 16)


class DemoProvider:
    nome = "demo"

    def __init__(self, dia_coleta: date | None = None):
        self.dia = dia_coleta or date.today()
        self.chamadas = 0
        self.falhas = 0

    def buscar(self, rota: Rota, mes: str) -> list[Oferta]:
        self.chamadas += 1
        rnd = random.Random(_semente(rota.chave, mes, self.dia.isoformat()))
        base = BASE[rota.regiao] * FATOR_ORIGEM.get(rota.origem, 1.0)
        base *= 0.85 + (_semente(rota.destino) % 30) / 100  # cada destino tem seu nível
        mes_num = int(mes[5:7])
        if mes_num in (1, 7, 12):
            base *= 1.18  # alta temporada
        ano, m = int(mes[:4]), mes_num
        inicio = date(ano, m, 1)
        ofertas = []
        for _ in range(3):
            dia = inicio + timedelta(days=rnd.randint(0, 27))
            if dia <= self.dia:
                continue
            preco = base * rnd.uniform(0.88, 1.15)
            # De vez em quando aparece uma promoção (mais rara que o comum)
            if rnd.random() < 0.035:
                preco *= rnd.uniform(0.45, 0.72)
            volta = None
            if rota.tipo == "ida_volta":
                volta = (dia + timedelta(days=rnd.choice([7, 10, 12, 15, 20]))).isoformat()
            ofertas.append(Oferta(
                fonte=self.nome,
                origem=rota.origem,
                destino=rota.destino,
                aeroporto_destino=rota.destino,
                regiao=rota.regiao,
                tipo=rota.tipo,
                preco=round(preco, 2),
                cia=rnd.choice(CIAS[rota.regiao]),
                ida=dia.isoformat(),
                volta=volta,
                escalas=rnd.choice([0, 1, 1, 2]) if rota.regiao != "nacional" else rnd.choice([0, 0, 1]),
                duracao_min=None,
                link_fonte=None,
            ))
        return ofertas
