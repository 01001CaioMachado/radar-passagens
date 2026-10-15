"""Histórico de preços em SQLite (data/historico.db).

Para o arquivo continuar pequeno, guardamos:
  - diario: o MENOR preço de cada rota, para cada mês de viagem, em cada dia de coleta;
  - ofertas: só as ofertas da última coleta (o que aparece no painel);
  - coletas: um registro por execução.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .providers.base import Oferta

ESQUEMA = """
CREATE TABLE IF NOT EXISTS coletas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iniciada_em TEXT NOT NULL,
    dia TEXT NOT NULL,
    fonte TEXT NOT NULL,
    chamadas INTEGER DEFAULT 0,
    falhas INTEGER DEFAULT 0,
    ofertas INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS diario (
    fonte TEXT NOT NULL,
    chave_rota TEXT NOT NULL,
    mes_ida TEXT NOT NULL,
    dia TEXT NOT NULL,
    preco_min REAL NOT NULL,
    PRIMARY KEY (fonte, chave_rota, mes_ida, dia)
);
CREATE TABLE IF NOT EXISTS ofertas (
    coleta_id INTEGER NOT NULL,
    dia TEXT NOT NULL,
    fonte TEXT NOT NULL,
    chave_rota TEXT NOT NULL,
    origem TEXT NOT NULL,
    destino TEXT NOT NULL,
    aeroporto_destino TEXT,
    regiao TEXT NOT NULL,
    tipo TEXT NOT NULL,
    preco REAL NOT NULL,
    cia TEXT,
    ida TEXT NOT NULL,
    volta TEXT,
    escalas INTEGER,
    duracao_min INTEGER,
    link_fonte TEXT
);
"""


class Historico:
    def __init__(self, caminho: Path):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(caminho)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)

    # ---------- gravação ----------
    def nova_coleta(self, fonte: str, dia: date | None = None) -> int:
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        dia = (dia or date.today()).isoformat()
        cur = self.con.execute(
            "INSERT INTO coletas (iniciada_em, dia, fonte) VALUES (?, ?, ?)", (agora, dia, fonte)
        )
        self.con.commit()
        return cur.lastrowid

    def salvar(self, coleta_id: int, ofertas: list[Oferta], chamadas: int, falhas: int) -> None:
        c = self.con.execute("SELECT dia, fonte FROM coletas WHERE id=?", (coleta_id,)).fetchone()
        dia, fonte = c["dia"], c["fonte"]
        if ofertas:
            # Painel mostra só a última coleta com resultado
            self.con.execute("DELETE FROM ofertas WHERE fonte=?", (fonte,))
            self.con.executemany(
                """INSERT INTO ofertas (coleta_id, dia, fonte, chave_rota, origem, destino, aeroporto_destino,
                   regiao, tipo, preco, cia, ida, volta, escalas, duracao_min, link_fonte)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(coleta_id, dia, o.fonte, o.chave_rota, o.origem, o.destino, o.aeroporto_destino,
                  o.regiao, o.tipo, o.preco, o.cia, o.ida, o.volta, o.escalas, o.duracao_min, o.link_fonte)
                 for o in ofertas],
            )
            minimos: dict[tuple, float] = {}
            for o in ofertas:
                k = (o.chave_rota, o.ida[:7])
                minimos[k] = min(o.preco, minimos.get(k, float("inf")))
            self.con.executemany(
                """INSERT INTO diario (fonte, chave_rota, mes_ida, dia, preco_min) VALUES (?,?,?,?,?)
                   ON CONFLICT(fonte, chave_rota, mes_ida, dia)
                   DO UPDATE SET preco_min = MIN(preco_min, excluded.preco_min)""",
                [(fonte, rota, mes, dia, p) for (rota, mes), p in minimos.items()],
            )
        self.con.execute(
            "UPDATE coletas SET chamadas=?, falhas=?, ofertas=? WHERE id=?",
            (chamadas, falhas, len(ofertas), coleta_id),
        )
        self.con.commit()

    # ---------- leitura ----------
    def ultima_coleta(self) -> sqlite3.Row | None:
        return self.con.execute(
            "SELECT * FROM coletas WHERE ofertas > 0 ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def ofertas_da_coleta(self, coleta_id: int) -> list[dict]:
        rows = self.con.execute("SELECT * FROM ofertas WHERE coleta_id=?", (coleta_id,)).fetchall()
        return [dict(r) for r in rows]

    def minimos_diarios(self, chave_rota: str, ate_dia: str, janela_dias: int, fonte: str,
                        mes_ida: str | None = None) -> list[tuple[str, float]]:
        """Menor preço de cada dia de coleta, ANTES do dia informado.
        Com mes_ida: só viagens naquele mês (compara temporada com temporada)."""
        inicio = (date.fromisoformat(ate_dia) - timedelta(days=janela_dias)).isoformat()
        sql = """SELECT dia, MIN(preco_min) AS p FROM diario
                 WHERE fonte=? AND chave_rota=? AND dia>=? AND dia<?"""
        args: list = [fonte, chave_rota, inicio, ate_dia]
        if mes_ida:
            sql += " AND mes_ida=?"
            args.append(mes_ida)
        rows = self.con.execute(sql + " GROUP BY dia ORDER BY dia", args).fetchall()
        return [(r["dia"], r["p"]) for r in rows]

    def serie_completa(self, fonte: str, ate_dia: str, janela_dias: int) -> dict[str, list[tuple[str, float]]]:
        """Menor preço diário por rota e mês de viagem ("GRU-LIS-ida_volta|2027-03"), para os gráficos."""
        inicio = (date.fromisoformat(ate_dia) - timedelta(days=janela_dias)).isoformat()
        rows = self.con.execute(
            """SELECT chave_rota, mes_ida, dia, preco_min AS p FROM diario
               WHERE fonte=? AND dia>=? AND dia<=? ORDER BY dia""",
            (fonte, inicio, ate_dia),
        ).fetchall()
        out: dict[str, list] = {}
        for r in rows:
            out.setdefault(f'{r["chave_rota"]}|{r["mes_ida"]}', []).append((r["dia"], round(r["p"], 2)))
        return out

    def minimo_historico(self, chave_rota: str, ate_dia: str, fonte: str) -> float | None:
        r = self.con.execute(
            "SELECT MIN(preco_min) AS p FROM diario WHERE fonte=? AND chave_rota=? AND dia<?",
            (fonte, chave_rota, ate_dia),
        ).fetchone()
        return r["p"] if r and r["p"] is not None else None

    # ---------- manutenção ----------
    def limpar_antigos(self, dias: int = 180) -> None:
        corte = (date.today() - timedelta(days=dias)).isoformat()
        self.con.execute("DELETE FROM diario WHERE dia < ?", (corte,))
        self.con.execute("DELETE FROM coletas WHERE dia < ?", (corte,))
        self.con.commit()

    def fechar(self) -> None:
        self.con.execute("VACUUM")
        self.con.close()
