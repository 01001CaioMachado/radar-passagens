from datetime import date, timedelta

import pytest

from radar import config as cfgmod
from radar.analise import analisar, avaliar_milhas, classificar
from radar.config import Rota
from radar.db import Historico
from radar.main import coletar, meses
from radar.providers import DemoProvider, TravelpayoutsProvider


@pytest.fixture
def cfg():
    return cfgmod.carregar()


def hist_fixo(precos):
    hoje = date(2026, 10, 14)
    return [((hoje - timedelta(days=i + 1)).isoformat(), p) for i, p in enumerate(precos)]


def test_classifica_pelo_historico(cfg):
    h = hist_fixo([4000] * 10)
    assert classificar(3900, "europa", h, cfg)["nivel"] == "normal"
    assert classificar(3200, "europa", h, cfg)["nivel"] == "boa"       # 20% abaixo
    assert classificar(2500, "europa", h, cfg)["nivel"] == "otima"     # 37,5% abaixo
    r = classificar(1700, "europa", h, cfg)                            # 57,5% abaixo
    assert r["nivel"] == "erro" and r["base"] == "historico" and r["preco_normal"] == 4000


def test_sem_historico_usa_referencia(cfg):
    r = classificar(2900, "europa", hist_fixo([4000, 4100]), cfg)
    assert r["base"] == "referencia" and r["nivel"] == "otima"
    assert classificar(3500, "europa", [], cfg)["nivel"] == "boa"
    assert classificar(5000, "europa", [], cfg)["nivel"] == "normal"


def test_milhas_tabela_fixa_nacional(cfg):
    # Trecho nacional R$ 900: (900-60)/7,5 = R$ 112/milheiro no AAdvantage -> usar milhas
    o = {"preco": 900, "regiao": "nacional", "tipo": "ida", "destino": "REC"}
    m = avaliar_milhas(o, cfg)
    aa = m["comparacoes"][0]
    assert aa["milhas"] == 7500 and aa["valor_milheiro"] == 112.0
    assert m["usar_milhas"] and m["teto_milhas"] == int(840 / 25 * 1000)


def test_milhas_europa_ida_volta_dobra_trechos(cfg):
    o = {"preco": 3600, "regiao": "europa", "tipo": "ida_volta", "destino": "LIS"}
    m = avaliar_milhas(o, cfg)
    progs = {c["programa"]: c for c in m["comparacoes"]}
    assert "Iberia Club (Avios)" not in progs                # Iberia só para MAD
    latam = progs["LATAM Pass (tabela fixa de parceiras)"]
    assert latam["milhas"] == 161400
    assert latam["valor_milheiro"] == round(3000 / 161400 * 1000, 2)
    assert not latam["vale"]


def test_milhas_sem_tabela_mostra_teto(cfg):
    o = {"preco": 1500, "regiao": "america_sul", "tipo": "ida_volta", "destino": "SCL"}
    m = avaliar_milhas(o, cfg)
    assert m["comparacoes"] == [] and m["teto_milhas"] == 50000
    assert "50.000" in m["veredito"]


def test_meses_vira_ano():
    assert meses(3, date(2026, 11, 20)) == ["2026-11", "2026-12", "2027-01"]


class FakeResp:
    def __init__(self, status, corpo):
        self.status_code, self._c = status, corpo

    def json(self):
        return self._c

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSessao:
    def __init__(self, respostas):
        self.respostas, self.headers, self.params = list(respostas), {}, []

    def get(self, url, params=None, timeout=None):
        self.params.append(params)
        return self.respostas.pop(0)


def test_travelpayouts_parse_e_filtra():
    futuro = (date.today() + timedelta(days=60)).isoformat()
    volta = (date.today() + timedelta(days=70)).isoformat()
    passado = (date.today() - timedelta(days=1)).isoformat()
    corpo = {"success": True, "currency": "brl", "data": [
        {"price": 3150, "airline": "TP", "departure_at": futuro + "T10:00:00-03:00",
         "return_at": volta + "T20:00:00+01:00", "transfers": 0, "return_transfers": 1,
         "destination_airport": "LIS", "link": "/search/GRU1012LIS2012"},
        {"price": 2000, "airline": "XX", "departure_at": passado + "T10:00:00-03:00", "return_at": volta},
        {"price": 1900, "airline": "YY", "departure_at": futuro + "T10:00:00-03:00"},  # sem volta
    ]}
    s = FakeSessao([FakeResp(429, {}), FakeResp(200, corpo)])
    p = TravelpayoutsProvider(token="x", pausa=0, sessao=s)
    import radar.providers.travelpayouts as tp
    tp.time.sleep = lambda *_: None
    of = p.buscar(Rota("GRU", "LIS", "europa", "ida_volta"), "2026-12")
    assert len(of) == 1
    o = of[0]
    assert (o.preco, o.escalas, o.volta, o.cia) == (3150.0, 1, volta, "TP")
    assert o.link_fonte == "https://www.aviasales.com/search/GRU1012LIS2012"
    assert s.params[-1]["one_way"] == "false" and s.params[-1]["currency"] == "brl"
    assert o.link_google().startswith("https://www.google.com/travel/flights")


def test_travelpayouts_rejeita_moeda_errada():
    corpo = {"success": True, "currency": "rub", "data": [{"price": 1, "departure_at": "2099-01-01"}]}
    p = TravelpayoutsProvider(token="x", pausa=0, sessao=FakeSessao([FakeResp(200, corpo)]))
    assert p.buscar(Rota("GRU", "REC", "nacional", "ida"), "2099-01") == []


def test_fluxo_completo_demo(tmp_path, cfg):
    cfg.meses_a_frente = 3
    h = Historico(tmp_path / "t.db")
    hoje = date.today()
    for i in range(10, -1, -1):
        d = hoje - timedelta(days=i)
        coletar(cfg, h, DemoProvider(d), d)
    dados = analisar(h, cfg)
    assert dados["coleta"]["dia"] == hoje.isoformat()
    of = dados["ofertas"]
    assert of and all(o["ida"] > hoje.isoformat() for o in of)
    # uma oferta por rota e mês
    chaves = [(o["chave_rota"], o["ida"][:7]) for o in of]
    assert len(chaves) == len(set(chaves))
    # oportunidades vêm primeiro
    rank = {"erro": 0, "otima": 1, "boa": 2, "normal": 3}
    niveis = [rank[o["nivel"]] for o in of]
    assert niveis == sorted(niveis)
    assert any(o["base"] == "historico" for o in of)
