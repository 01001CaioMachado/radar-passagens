"""Formato comum de uma oferta encontrada por qualquer fonte de preços."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import quote


def link_google(origem: str, destino: str, ida: str, volta: str | None) -> str:
    """Link de busca no Google Flights para conferir o preço antes de comprar."""
    q = f"Flights to {destino} from {origem} on {ida}"
    if volta:
        q += f" through {volta}"
    else:
        q += " oneway"
    return "https://www.google.com/travel/flights?hl=pt-BR&curr=BRL&q=" + quote(q)


@dataclass
class Oferta:
    fonte: str
    origem: str           # aeroporto de saída pedido (GRU, VCP, ...)
    destino: str          # código do destino pedido (LIS, PAR, ...)
    aeroporto_destino: str
    regiao: str
    tipo: str             # "ida" ou "ida_volta"
    preco: float          # total em R$ (ida e volta quando tipo = ida_volta)
    cia: str
    ida: str              # AAAA-MM-DD
    volta: str | None
    escalas: int
    duracao_min: int | None
    link_fonte: str | None = None

    @property
    def chave_rota(self) -> str:
        return f"{self.origem}-{self.destino}-{self.tipo}"

    def link_google(self) -> str:
        return link_google(self.origem, self.aeroporto_destino or self.destino, self.ida, self.volta)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["chave_rota"] = self.chave_rota
        d["link_google"] = self.link_google()
        return d
