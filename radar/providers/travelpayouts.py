"""Fonte gratuita de preços em reais: Travelpayouts / Aviasales Data API.

Os preços vêm do cache de buscas reais feitas no Aviasales nos últimos dias.
Por isso cada oferta leva um link para conferir no Google Flights antes de comprar.
Token grátis em https://www.travelpayouts.com (Ferramentas > API).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date

import requests

from ..config import Rota
from .base import Oferta

log = logging.getLogger(__name__)

URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
AVIASALES = "https://www.aviasales.com"


class TravelpayoutsProvider:
    nome = "travelpayouts"

    def __init__(self, token: str | None = None, pausa: float = 0.2, sessao: requests.Session | None = None):
        self.token = token or os.environ.get("TRAVELPAYOUTS_TOKEN", "")
        if not self.token:
            raise RuntimeError(
                "Falta o token. Crie um grátis em travelpayouts.com e salve como "
                "secret TRAVELPAYOUTS_TOKEN no GitHub."
            )
        self.pausa = pausa
        self.sessao = sessao or requests.Session()
        self.sessao.headers.update({"X-Access-Token": self.token, "Accept-Encoding": "gzip"})
        self.chamadas = 0
        self.falhas = 0

    def _get(self, params: dict) -> list[dict]:
        for tentativa in range(4):
            try:
                r = self.sessao.get(URL, params=params, timeout=30)
                self.chamadas += 1
                if r.status_code == 429:
                    espera = 5 * (tentativa + 1)
                    log.warning("Limite de requisições; aguardando %ss", espera)
                    time.sleep(espera)
                    continue
                r.raise_for_status()
                corpo = r.json()
                if not corpo.get("success", False):
                    log.warning("API respondeu erro: %s", corpo.get("error"))
                    return []
                moeda = (corpo.get("currency") or "brl").lower()
                if moeda != "brl":
                    log.warning("Moeda inesperada %s; ignorando resposta", moeda)
                    return []
                return corpo.get("data") or []
            except (requests.RequestException, ValueError) as e:
                log.warning("Falha na chamada (%s): %s", tentativa + 1, e)
                time.sleep(2 * (tentativa + 1))
        self.falhas += 1
        return []

    def buscar(self, rota: Rota, mes: str) -> list[Oferta]:
        params = {
            "origin": rota.origem,
            "destination": rota.destino,
            "departure_at": mes,
            "currency": "brl",
            "market": "br",
            "sorting": "price",
            "limit": 10,
            "one_way": "true" if rota.tipo == "ida" else "false",
        }
        itens = self._get(params)
        time.sleep(self.pausa)
        hoje = date.today().isoformat()
        ofertas = []
        for it in itens:
            ida = (it.get("departure_at") or "")[:10]
            volta = (it.get("return_at") or "")[:10] or None
            if not ida or ida < hoje:
                continue
            if rota.tipo == "ida_volta" and not volta:
                continue  # queremos só ida e volta nessas regiões
            preco = it.get("price")
            if not preco or preco <= 0:
                continue
            escalas = int(it.get("transfers") or 0) + int(it.get("return_transfers") or 0)
            link = it.get("link")
            ofertas.append(Oferta(
                fonte=self.nome,
                origem=rota.origem,
                destino=rota.destino,
                aeroporto_destino=it.get("destination_airport") or rota.destino,
                regiao=rota.regiao,
                tipo=rota.tipo,
                preco=float(preco),
                cia=it.get("airline") or "?",
                ida=ida,
                volta=volta,
                escalas=escalas,
                duracao_min=it.get("duration"),
                link_fonte=(AVIASALES + link) if link else None,
            ))
        return ofertas
