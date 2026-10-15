# Radar de Passagens

Procura passagens baratas saindo de **Guarulhos, Congonhas, Campinas (Viracopos), Ribeirão Preto e São José do Rio Preto** para Europa, EUA, América do Sul e destinos nacionais, 3 vezes por dia, e publica um painel no seu próprio site gratuito.

Para cada preço, o radar responde duas perguntas:

1. **Este preço é bom de verdade?** Compara com o histórico da mesma rota, no mesmo mês de viagem (dezembro com dezembro). Só marca como oportunidade o que estiver 20% ou mais abaixo do normal.
2. **Vale pagar em reais ou em milhas?** Diz até quantas milhas vale a pena gastar naquela passagem e compara com tabelas fixas públicas (AAdvantage na GOL, Iberia, tabela fixa LATAM Pass).

Custo: **zero** (GitHub gratuito + API gratuita).

---

## Como colocar no ar (uns 15 minutos, pelo computador)

### Passo 1 — Criar o repositório no GitHub

1. Crie uma conta em [github.com](https://github.com) (se ainda não tiver).
2. Clique em **New repository**. Nome: `radar-passagens`. Marque **Public** (o site gratuito do GitHub exige repositório público no plano grátis). Clique em **Create repository**.
3. Na página do repositório, clique em **uploading an existing file**, descompacte o `.zip` no computador e arraste **todo o conteúdo da pasta** `radar-passagens` (não a pasta em si). Clique em **Commit changes**.

> Atenção: a pasta `.github` começa com ponto e pode ficar escondida. No Mac, aperte `Cmd + Shift + .` no Finder para mostrar; no Windows, ative "Itens ocultos" no menu Exibir. Sem ela, nada roda sozinho. Confira se aparece `.github/workflows/radar.yml` no repositório depois do envio.

### Passo 2 — Pegar o token gratuito de preços

1. Crie uma conta em [travelpayouts.com](https://www.travelpayouts.com).
2. No painel, vá em **Ferramentas → API** (Tools → API) e copie o **token**.
3. No GitHub, no seu repositório: **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `TRAVELPAYOUTS_TOKEN`
   - Secret: cole o token
   - **Add secret**

### Passo 3 — Ligar o site

**Settings → Pages → Build and deployment → Source: GitHub Actions.**

### Passo 4 — Rodar pela primeira vez

**Actions → Radar → Run workflow → Run workflow.** Leva uns 5 a 10 minutos.

Quando terminar, seu painel fica em:

```
https://SEU-USUARIO.github.io/radar-passagens/
```

Salve esse link na tela inicial do celular. A partir daí ele se atualiza sozinho às ~6h47, 12h47 e 19h47.

> Sem o token, o workflow publica um painel de **demonstração** com preços fictícios (com aviso amarelo no topo). Serve para ver como fica antes de configurar.

---

## Primeiros dias: o que esperar

- **Dias 1 a 4:** ainda não há histórico. O radar usa os preços de referência de `config.yaml` para apontar oportunidades. São estimativas iniciais; ajuste se achar que estão altas ou baixas.
- **A partir do 5º dia de coleta:** passa a comparar com o histórico real de cada rota e mês de viagem. É aqui que as "oportunidades reais" começam a aparecer com confiança.
- **Possível erro tarifário:** preço 55%+ abaixo do normal. Confira rápido no Google Flights — costuma sumir em horas.

## Antes de comprar

Os preços vêm de buscas recentes de outros usuários no Aviasales (podem ter algumas horas ou dias). **Toda oferta tem o botão "Conferir no Google Flights"** para ver o preço atual antes de comprar.

## Como ler a parte de milhas

O radar não entra na LATAM, Smiles ou Azul (eles não têm API pública e o preço deles muda por demanda). Ele faz duas contas:

- **Teto de milhas:** `(preço em reais − taxas) ÷ valor mínimo do milheiro`. Exemplo: passagem de R$ 3.600 para a Europa, taxas de R$ 600, mínimo de R$ 25 → só emita com milhas se custar até **120.000 milhas** + taxas. Busque no app do programa e compare.
- **Tabelas fixas** (`milhas_referencia.yaml`): mostra quanto cada milheiro renderia na AAdvantage (GOL nacional por 7.500), Iberia (Madri) e tabela fixa LATAM Pass/AAdvantage para Europa. Em verde quando passa do seu mínimo.

Ajuste em `config.yaml`, seção `milhas`:
- `meu_custo_milheiro`: quanto você paga por mil milhas;
- `valor_minimo_milheiro`: abaixo disso, prefira pagar em reais;
- `taxas_estimadas`: taxas de embarque por região.

## Personalizar

Tudo em `config.yaml` (edite pelo GitHub clicando no arquivo e no lápis):

| O quê | Onde |
|---|---|
| Incluir/remover aeroportos de saída | `origens` |
| Incluir/remover destinos | `regioes → destinos` (código IATA de 3 letras) |
| Quantos meses à frente procurar | `meses_a_frente` |
| Quão "barato" precisa ser | `oportunidade` (20% / 35% / 55%) |
| Preço de referência nos primeiros dias | `referencia_inicial` |

Horários das buscas: `.github/workflows/radar.yml`, linhas `cron` (em UTC, 3 horas à frente de Brasília).

## Manutenção

- O GitHub pode **pausar agendamentos** de repositórios públicos sem atividade por 60 dias. Se o painel parar de atualizar, abra **Actions → Radar** e clique em **Enable workflow**.
- O histórico fica no branch `dados` (substituído a cada execução, então o repositório não cresce). Guardamos 180 dias.
- As tabelas fixas de milhas mudam sem aviso. Revise `milhas_referencia.yaml` de tempos em tempos.

## Rodar no computador (opcional)

```bash
pip install -r requirements.txt
python -m radar.main demo        # painel de demonstração em site/index.html
export TRAVELPAYOUTS_TOKEN=seu_token
python -m radar.main tudo        # coleta real + painel
python -m pytest                 # testes
```

## Como funciona por dentro

```
radar/
  providers/travelpayouts.py  busca preços em R$ (API gratuita Aviasales)
  providers/demo.py           preços fictícios para teste
  db.py                       histórico: menor preço por rota, mês de viagem e dia
  analise.py                  decide o que é oportunidade e calcula milhas
  painel.py + templates/      gera o site
  main.py                     comandos: coletar, painel, tudo, demo
config.yaml                   suas preferências
milhas_referencia.yaml        tabelas fixas de milhas (com fontes)
```

Para cada rota (ex.: Campinas → Lisboa, ida e volta) e cada um dos próximos meses, o radar guarda o menor preço do dia. O "preço normal" é a mediana dos últimos 60 dias para aquele mesmo mês de viagem; o preço atual é comparado com ele.
