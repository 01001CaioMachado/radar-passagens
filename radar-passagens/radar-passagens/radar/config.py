"""Leitura da configuração do Radar de Passagens."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent


@dataclass
class Rota:
    origem: str
    destino: str
    regiao: str
    tipo: str  # "ida" ou "ida_volta"

    @property
    def chave(self) -> str:
        return f"{self.origem}-{self.destino}-{self.tipo}"


@dataclass
class Config:
    origens: dict[str, str]
    regioes: dict[str, dict]
    meses_a_frente: int
    oportunidade: dict
    referencia_inicial: dict
    milhas: dict
    tabelas_milhas: list[dict] = field(default_factory=list)

    def rotas(self) -> list[Rota]:
        out = []
        for reg_id, reg in self.regioes.items():
            for dest in reg["destinos"]:
                for orig in self.origens:
                    out.append(Rota(orig, dest, reg_id, reg.get("tipo", "ida_volta")))
        return out

    def nome_destino(self, iata: str) -> str:
        for reg in self.regioes.values():
            if iata in reg["destinos"]:
                return reg["destinos"][iata]
        return iata

    def nome_origem(self, iata: str) -> str:
        return self.origens.get(iata, iata)


def carregar(caminho: Path | None = None, tabelas: Path | None = None) -> Config:
    caminho = caminho or RAIZ / "config.yaml"
    tabelas = tabelas or RAIZ / "milhas_referencia.yaml"
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    tab = yaml.safe_load(tabelas.read_text(encoding="utf-8")) if tabelas.exists() else []
    return Config(
        origens=dados["origens"],
        regioes=dados["regioes"],
        meses_a_frente=int(dados.get("meses_a_frente", 8)),
        oportunidade=dados["oportunidade"],
        referencia_inicial=dados["referencia_inicial"],
        milhas=dados["milhas"],
        tabelas_milhas=tab or [],
    )
