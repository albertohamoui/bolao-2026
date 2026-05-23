# BOLÃO 2026 — Documentação Técnica

**Tempo de execução:** ~6 segundos para pipeline completo com 50.000 simulações Monte Carlo
**Última atualização:** 23 de maio de 2026

---

## SUMÁRIO

1. [Introdução e Contexto](#1-introdução-e-contexto)
2. [Visão Geral da Arquitetura](#2-visão-geral-da-arquitetura)
3. [Componentes do Modelo](#3-componentes-do-modelo)
   - 3.1 [Dixon-Coles](#31-modelo-dixon-coles)
   - 3.2 [Blend Bayesiano de 3 Canais](#32-blend-bayesiano-de-3-canais)
   - 3.3 [Simulação Monte Carlo](#33-simulação-monte-carlo)
   - 3.4 [Host Advantage](#34-host-advantage)
   - 3.5 [Expert Adjustments](#35-expert-adjustments)
   - 3.6 [EV-Optimal Score](#36-ev-optimal-score)
   - 3.7 [Tournament Factor](#37-tournament-factor)
   - 3.8 [Modelo de Escalação](#38-modelo-de-escalação)
   - 3.9 [Modelo de Artilheiro](#39-modelo-de-artilheiro)
4. [Regras do Bolão e Sistema de Pontuação](#4-regras-do-bolão-e-sistema-de-pontuação)
5. [Dados e Fontes](#5-dados-e-fontes)
6. [Como Rodar](#6-como-rodar)
7. [Output e Interpretação](#7-output-e-interpretação)
8. [Forças do Modelo](#8-forças-do-modelo)
9. [Fraquezas e Limitações](#9-fraquezas-e-limitações)
10. [Roadmap de Melhorias](#10-roadmap-de-melhorias)
11. [Apêndice Técnico](#11-apêndice-técnico)

---

## 1. Introdução e Contexto

### 1.1 O que é o projeto

Modelo estatístico para prever resultados da Copa do Mundo FIFA 2026, construído para o Bolão do Zap (bolaodozap.com). O bolão exige:

- **Placar exato** de cada um dos 72 jogos da fase de grupos
- **Classificação dos grupos** (1º, 2º colocados e 8 melhores 3ºs) — derivada automaticamente pelo sistema do bolão a partir dos placares apostados, usando critérios FIFA (pontos → saldo → confronto direto). Não são palpites independentes.
- **Palpite de campeão** da Copa (seleção)
- **Palpite de artilheiro** da Copa (jogador — nome deve coincidir exatamente com a camisa)
- **Placar exato** dos 31 jogos do mata-mata (bracket preenchido inteiro de uma vez após a fase de grupos) + escolha de quem avança em caso de palpite de empate

### 1.2 Calendário e deadlines

O bolão tem duas fases de submissão:

**Fase 1 — Deadline: 7 de junho de 2026, 23h59**

| Palpite | Detalhe |
|---|---|
| Placares dos 72 jogos da fase de grupos | Preenchidos no site, grupo a grupo |
| Classificação dos grupos (1º, 2º) e 8 melhores 3ºs | Derivados automaticamente pelos placares |
| Campeão da Copa | Palpite direto (seleção) |
| Artilheiro da Copa | Palpite direto (nome do jogador, como na camisa) |

**Fase 2 — Após 27 de junho de 2026 (pós-fase de grupos)**

| Palpite | Detalhe |
|---|---|
| Bracket completo do mata-mata (31 jogos) | Placar de todos os jogos eliminatórios de uma vez. O vencedor avança automaticamente. |
| Quem passa nos pênaltis | Campo aberto em caso de placar empatado |

**Datas do torneio:** abertura 11/6, encerramento de grupos 27/6, final 19/7/2026.

### 1.3 Formato da Copa 2026

- **48 seleções** em **12 grupos de 4** — 72 jogos na fase de grupos
- Top 2 de cada grupo (24) + 8 melhores 3ºs = 32 classificadas
- **Mata-mata:** R32, R16, Quartas, Semis, 3º lugar, Final — 32 jogos (31 no bracket + 1 disputa de 3º lugar não coberta pelo bolão)
- **Total:** 104 jogos em ~39 dias

### 1.4 Por que um modelo estatístico

72 placares exatos antes da Copa começar. Decisões por feeling têm variância alta. Um modelo calibrado integra múltiplas fontes de informação, minimiza vieses emocionais, e otimiza pontuação esperada (não só "qual placar acho provável").

---

## 2. Visão Geral da Arquitetura

### 2.1 Diagrama de alto nível

```
┌─────────────────────────────────────────────────────────────┐
│ DADOS DE ENTRADA                                            │
│  49.215 jogos históricos   Elo Ratings (48 seleções)        │
│  Transfermarkt (48 seleções, valor €M)                      │
│  Grupos oficiais (sorteio dez/25)   Sedes host (9 jogos)    │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ CALIBRAÇÃO                                                   │
│  Filtro: jogos desde 01/01/2022 (~512 entre seleções da Copa)│
│  Dixon-Coles MLE com time-decay + filtro de qualidade        │
│  Blend bayesiano: 45% DC + 30% Elo + 25% TM                 │
│  [Opcional: Tournament Factor, Escalação]                    │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ PREDIÇÃO POR JOGO                                            │
│  λ_h = exp(α_home + β_away + host_adv)                      │
│  μ_a = exp(α_away + β_home)                                 │
│  P(h=i, a=j) = Pois(i;λ) × Pois(j;μ) × τ(i,j)             │
│  → matriz 8×8 de probabilidades de placar                    │
└───────────┬─────────────────────────────────┬───────────────┘
            ▼                                 ▼
┌────────────────────┐           ┌────────────────────────────┐
│ EV-OPTIMAL SCORE   │           │ MONTE CARLO (50k sims)     │
│ max EV = Σ P(i,j)  │           │ Torneio inteiro simulado   │
│  × pontos_bolão    │           │ → P(título), P(fase), etc  │
└────────────────────┘           └────────────────────────────┘
```

### 2.2 Princípios arquiteturais

1. **Zero duplicidade.** Cada canal mede algo diferente: Elo (força ponderada por adversário), TM (qualidade individual), DC (forma recente e estilo).
2. **Convergência com mercado.** Divergência grande indica bug, não insight.
3. **Performance.** Pipeline completo em ~6 segundos.
4. **Expert adjustments são residuais.** Só para fatores que os dados não capturam.

---

## 3. Componentes do Modelo

### 3.1 Modelo Dixon-Coles

#### 3.1.1 Teoria

O modelo Dixon-Coles (1997) é o padrão da indústria para predição de futebol:

1. Cada seleção tem parâmetros de **ataque (α)** e **defesa (β)**
2. Gols seguem distribuições Poisson: `λ_home = exp(α_home + β_away + home_adv)`, `μ_away = exp(α_away + β_home)`
3. Probabilidade conjunta de placar: `P(h=i, a=j) = Pois(i;λ) × Pois(j;μ) × τ(i,j)`

#### 3.1.2 Correção tau (τ)

O Poisson puro subestima placares baixos (0-0, 1-0, 0-1, 1-1). A correção τ ajusta:

```python
τ(0,0) = 1 - λμρ;  τ(0,1) = 1 + λρ;  τ(1,0) = 1 + μρ;  τ(1,1) = 1 - ρ
```

Para `(i,j)` fora de {0,1}×{0,1}, τ = 1.0. O parâmetro ρ é estimado pela MLE (atual: ρ ≈ -0.12).

#### 3.1.3 Time-decay

Jogos recentes pesam mais: `weight = exp(-xi × (data_mais_recente - data_jogo))`. Com xi = 0.001, um jogo de 1 ano atrás pesa 69% de um jogo de hoje; 2 anos, 48%; 5 anos, 16%.

#### 3.1.4 Filtro de qualidade de adversário

Jogos entre adversários muito desiguais inflam parâmetros de ataque do favorito. O filtro reduz o peso desses jogos, multiplicativo com o time-decay:

| Gap de Elo | Peso |
|---|---|
| > 300 (ex: Spain vs Qatar, gap 740) | 0.2 |
| > 200 (ex: France vs Tunisia, gap 446) | 0.5 |
| > 100 | 0.8 |
| ≤ 100 | 1.0 |

Entre os 512 jogos da calibração, 333 são afetados (62 com gap > 300). Configurável via `config.json → dc_quality_filter`. Com `enabled: false`, apenas time-decay é aplicado.

O gap de Elo usado é o atual (não o do momento do jogo) — aproximação aceitável porque Elos mudam lentamente.

#### 3.1.5 Função de likelihood

```
-log L = -Σ w_i × [log(τ) + hg×log(λ) - λ + ag×log(μ) - μ] + 100×(Σα)²
```

A penalty `100×(Σα)²` garante identificabilidade (soma dos ataques = 0).

#### 3.1.6 Parâmetros default

| Parâmetro | Valor | Descrição |
|---|---|---|
| `xi` | 0.001 | Time decay |
| `home_adv` (inicial) | 0.25 | Ajustada pela MLE; atual calibrada: ~0.168 |
| `rho` (inicial) | -0.05 | Ajustada pela MLE; atual calibrada: ~-0.12 |
| `date_cutoff` | 2022-01-01 | Janela de dados |

#### 3.1.7 Viés residual do DC

O DC tem viés de adversário: seleções que jogam muito contra fracos (Brasil vs CONMEBOL, Japão vs AFC) ficam com ataque inflado; seleções com resultados medianos contra iguais (Inglaterra em amistosos/qualifiers) ficam deflacionadas. O blend bayesiano (§3.2) e o filtro de qualidade (§3.1.4) atenuam mas não eliminam esse viés. Na calibração atual, o Brasil tem α_DC = +0.586 (6º) e a Inglaterra α_DC = +0.187 (17º — subestimada significativamente).

### 3.2 Blend Bayesiano de 3 Canais

#### 3.2.1 Três canais complementares

| Canal | Mede | Viés principal |
|---|---|---|
| **Dixon-Coles** | Forma recente + estilo | Viés de adversário |
| **Elo** | Força geral ponderada | Lag temporal (demora a refletir mudanças) |
| **Transfermarkt** | Qualidade individual | Não vê entrosamento tático |

Combinar os 3 atenua o viés de cada um: Elo corrige o viés de adversário do DC, TM compensa o lag do Elo, DC corrige o fato de que TM não vê forma atual.

#### 3.2.2 Formulação

```
α_final[t] = 0.45 × α_DC[t] + 0.30 × α_Elo[t] + 0.25 × α_TM[t]
β_final[t] = 0.45 × β_DC[t] + 0.30 × β_Elo[t] + 0.25 × β_TM[t]
```

Pesos: **45% DC + 30% Elo + 25% TM** (devem somar 1.0).

**Justificativa dos pesos:** DC é o mais rico em informação mas o mais enviesado (peso moderado). Elo é estável mas com lag (peso menor). TM é o canal mais independente (peso crescente para corrigir vieses de resultado). Os pesos não foram calibrados por backtest formal — é uma área de melhoria pendente (ver §10).

#### 3.2.3 Priors do Elo

```python
strength = (elo[t] - elo_mean) / 400.0  # elo_mean ≈ 1780
elo_attack[t] = strength × 0.6;  elo_defense[t] = -strength × 0.4
```

A proporção 60/40 reflete a convenção de que "força" é mais atacante que defensiva.

#### 3.2.4 Priors do Transfermarkt

Escala sqrt para evitar que o topo domine (log comprime demais, linear amplifica demais):

```python
z = (sqrt(TM[t]) - mean) / std;  strength = z × 0.5
tm_attack[t] = strength × 0.6;  tm_defense[t] = -strength × 0.4
```

O multiplicador 0.5 calibra o range do TM (~[-0.5, +0.5]) para ser comparável ao do Elo.

### 3.3 Simulação Monte Carlo

#### 3.3.1 O que simula

50.000 torneios completos (fase de grupos + mata-mata), cada um com resultados aleatórios sampleados das distribuições Poisson. Agrega:

- P(1º/2º/3º colocado) por grupo
- P(alcança cada fase: R32, R16, QF, SF, Final)
- P(campeão)
- Distribuição conjunta top-2 por grupo (para otimização de classificação)

#### 3.3.2 Fase de grupos

Round-robin com pontuação FIFA (3-1-0). Tiebreakers: pontos → saldo → gols pró → Elo (convenção do modelo; FIFA usa critérios adicionais).

#### 3.3.3 Mata-mata

5 fases: R32 (32→16), R16 (16→8), QF (8→4), SF (4→2), Final (2→1). A Copa 2026 tem disputa de 3º lugar, mas o bolão não a cobre — o MC não a simula.

Classificação pro R32: top 2 de cada grupo (24) + 8 melhores 3ºs. Pareamento simplificado (sequencial por grupo — **não respeita** a chave FIFA real; limitação conhecida, ver §9).

**Prorrogação e pênaltis:** em caso de empate, 30 minutos adicionais (λ/3) seguidos de pênaltis com viés leve baseado em Elo (~50/50, clippado entre 35-65%).

#### 3.3.4 Cache de lambdas

48 × 47 = 2.256 predições pré-calculadas antes do loop MC. As 50k simulações são O(1) por jogo.

### 3.4 Host Advantage

Dois parâmetros distintos:

- **`home_adv` ≈ 0.168:** calibrado pela MLE sobre todos os jogos internacionais. Afeta λ na calibração.
- **`wc_host_adv` = 0.12:** constante fixa aplicada apenas aos **9 jogos** onde um host joga em seu próprio país (+12.7% no λ do mandante). Tunável via config.json.

Os 9 jogos: México (3 jogos em casa), Canadá (3), Estados Unidos (3). No mata-mata, todos os jogos são neutros (simplificação — hosts têm probabilidade baixa de chegar longe).

**Decisão explícita:** altitude e temperatura NÃO são modeladas separadamente. A vantagem de mando do México já absorve implicitamente o efeito altitude da Cidade do México.

### 3.5 Expert Adjustments

Multiplicadores manuais por seleção no λ de ataque, via `config.json → expert_adjustments`. Uso recomendado: lesão do craque, troca de técnico, conflito interno. **Nunca** para corrigir erros do modelo. Aplica-se por seleção (não por jogo) e apenas `attack_mult` está ativo.

### 3.6 EV-Optimal Score

#### 3.6.1 O problema

O placar mais provável (modal) frequentemente é empate 1-1, mesmo quando P(home vence) = 60%. Apostar no modal desperdiça os tiers parciais do bolão.

#### 3.6.2 A solução

Maximizar valor esperado de pontos do bolão, não probabilidade de acerto exato:

```
bet_otima = argmax_{(a,b)} Σ P(i,j) × pontos_bolão((a,b), (i,j))
```

Custo: 8⁴ = 4.096 operações por jogo, ~20ms para 72 jogos.

#### 3.6.3 Função de pontos

Tiers mutuamente exclusivos (o mais alto aplica). Grupos / mata-mata:

| Critério | Grupos | Mata-mata |
|---|---|---|
| Placar exato | 10 | 15 |
| Diferença de gols | 6 | 9 |
| Gols do vencedor | 5 | 8 |
| Gols do perdedor | 4 | 6 |
| Só o vencedor | 3 | 5 |
| Empate exato | 10 | 15 |
| Empate placar errado | 6 | 9 |
| Errou | 0 | 0 |

No mata-mata, o placar é avaliado após 90/120 min. Empate conta como empate para pontuação, independente de quem ganhe nos pênaltis.

#### 3.6.4 Efeito prático

~18 dos 72 jogos divergem entre modal e EV-optimal. O EV-optimal aposta em **vitórias de favoritos** em vez de empates seguros, porque os tiers parciais (DG=6, GV=5, GP=4) compensam o risco de errar o exato.

### 3.7 Tournament Factor

**Status: implementado, desligado por default (`enabled: false`).**

Ajuste residual pós-blend baseado em saldo de gols em torneios curtos (Copas, Euros, Copa América desde 2014), com peso maior em fases de mata-mata.

**Fórmula:**
```
TF = (saldo_rel_grupos + ko_weight × saldo_rel_ko) / (n_grupos + ko_weight × n_ko)
```
Centralizado subtraindo a média (remove viés sistemático do modelo). Aplicado em α e β com sinais opostos: `α *= (1 + TF × weight)`, `β *= (1 - TF × weight)`.

**Por que desligado:** validação empírica mostrou impacto marginal (<±0.2 pp em probabilidade de título). A métrica baseada em saldo de gols não captura adequadamente o fenômeno "Brasil marca muito em grupos mas perde em mata-mata" — o saldo de grupos altíssimo (+1.262) compensa o mata-mata negativo (-0.248), resultando em TF final positivo. Aumentar ko_weight para inverter seria ajuste ad-hoc sem calibração.

**Código preservado.** Reativação via `config.json → tournament_factor.enabled: true` quando backtest formal justificar.

### 3.8 Modelo de Escalação

**Status: implementado, desligado por default (`enabled: false`).**

Ajusta α e β pelo ratio `valor_convocação / valor_plantel_ideal`. Captura o impacto de lesões e ausências na convocação real.

**Fórmula:** `mult = 1 + weight × (raw_mult - 1)`, onde `raw_mult = Σ(value convocados) / ideal_squad_value`. O smoothing (weight = 0.5 default) evita que escalação 20% pior puxe α/β 20% — o coletivo compensa parcialmente. Com `use_top_11 = true`, soma apenas os 11 de maior valor.

**Quando ativar:** após convocações FIFA (~01/jun/2026). Preencher `convocated_squads` no config.json com dados do transfermarkt.com.

**Limitação:** multiplicador uniforme em α e β. Perder um atacante deveria afetar mais α que β. Simplicação aceitável para V1.

### 3.9 Modelo de Artilheiro

**Status: implementado, desligado por default (`enabled: false`).**

Sorteia o autor de cada gol dentro do Monte Carlo, em 3 etapas:

1. **Sorteia posição:** ATK 75%, MID 15%, DEF 10% (configurável)
2. **Sorteia jogador** dentro da posição, com peso `goals_season + 0.7 × xg_season` + regularização bayesiana (`k = 5`) + ruído gaussiano por simulação (`σ = 0.2`)
3. **Identifica artilheiro** ao final de cada simulação

O ruído é sorteado **uma vez por simulação** (não por gol) — cada Copa simulada tem um "dia" fixo para cada jogador. Overhead: ~5-6s adicionais para 50k simulações com 2-3 times.

**Quando ativar:** após preencher `player_stats` no config.json com dados por jogador (nome, posição, goals_season, xg_season, value_eur_m).

**Limitações:** independência entre gols, cobertura parcial (só times com dados), sem modelagem por oponente.

---

## 4. Regras do Bolão e Sistema de Pontuação

*Fonte: manual_bolao_do_zap.pdf. Gabarito canônico: bolao_regras_oficiais_v2.md.*

### 4.1 Placares — fase de grupos

Ver tabela em §3.6.3 (coluna Grupos).

### 4.2 Placares — mata-mata

Ver tabela em §3.6.3 (coluna Mata-mata). Empate conta como empate para pontuação, independente de pênaltis.

### 4.3 Bônus de classificação (derivados dos placares)

| Resultado | Pontos |
|---|---|
| 1º colocado na posição exata | 10 |
| 2º colocado na posição exata | 10 |
| Classificou mas posição trocada (1º↔2º) | 5 |
| Cada 3º colocado acertado (entre os 8 que avançam) | 5 |

Máximo: 240 pts (classificação) + 40 pts (3ºs). **Estes são consequência dos placares apostados**, não palpites independentes.

### 4.4 Bônus do mata-mata

| Resultado | Pontos |
|---|---|
| Acertou o time que avançou (qualquer fase) | 10 |

Flat por confronto (R32 a Final). Máximo: 310 pts. Bracket preenchido inteiro de uma vez após 27/6.

### 4.5 Bônus especiais

| Bônus | Pontos |
|---|---|
| Campeão | 25 |
| Artilheiro (nome = camisa) | 30 |

Deadline: 7/6 (separado do bracket).

### 4.6 Pontuação máxima teórica: 1830 pts

720 (placares grupos) + 240 (classificação) + 40 (3ºs) + 465 (placares mata-mata) + 310 (avanço) + 25 (campeão) + 30 (artilheiro).

---

## 5. Dados e Fontes

### 5.1 Dados históricos (results.csv)

- **Fonte:** github.com/martj42/international_results — 49.215 jogos (1872-2025)
- **Filtro para calibração:** `date >= 2022-01-01` → ~4.414 jogos, ~512 entre seleções da Copa

### 5.2 Elo Ratings

- **Fonte:** eloratings.net (coleta: 23/abr/2026)
- **Armazenamento:** `config.json → elo_ratings` (runtime) + `DEFAULT_ELO_RATINGS` em `bolao2026.py` (fallback)
- **Range:** 1425 (Qatar) a 2165 (Espanha)
- **Atualização:** manual via `scripts/diff_elos.py`. Scraping automático rejeitado por design (JavaScript-renderizado, validação humana valiosa).

### 5.3 Transfermarkt Values

- **Fonte:** transfermarkt.com (março 2026), em milhões de euros
- **Range:** €12M (Curaçao) a €1.3B (Inglaterra)
- **Top 30:** valores reais; restante: estimativas proporcionais ao Elo

### 5.4 Grupos oficiais e sedes

- Grupos: sorteio FIFA de 5/dez/2025
- Sedes host: 9 jogos hardcoded (3 por co-anfitrião)

---

## 6. Como Rodar

### 6.1 CLI

```bash
pip install numpy scipy pandas
python3 bolao2026.py --download   # primeira vez: baixa results.csv
python3 bolao2026.py              # pipeline completo (~6s)
```

### 6.2 Configuração

Todos os parâmetros estão em `config.json` (criado automaticamente com defaults na primeira execução). Classe `Calibration` valida ao carregar.

| Campo | Descrição |
|---|---|
| `w_dc`, `w_elo`, `w_tm` | Pesos do blend (devem somar 1.0) |
| `xi` | Time-decay |
| `wc_host_adv` | Vantagem de mando na Copa |
| `n_sims` | Simulações Monte Carlo |
| `dc_quality_filter` | Filtro de qualidade no DC (enabled por default) |
| `tournament_factor` | Tournament factor (disabled por default) |
| `squad_data` | Modelo de escalação (disabled por default) |
| `top_scorer_model` | Modelo de artilheiro (disabled por default) |

### 6.3 Streamlit

```bash
pip install streamlit
streamlit run app.py
```

Interface gráfica com 7 sub-tabs: Presets, Pesos & Hiperparâmetros, Features Opcionais, Elo Ratings, Transfermarkt, Expert Adjustments, Revisão & Salvar.

**Presets disponíveis:**
- **Modo Legacy:** todas as features opcionais desligadas
- **Modo Produção:** filtro de qualidade DC ativo, restante desligado

**Não exposto no app (por design):** dados históricos, convocações, player_stats, ideal_squad_values — são dados, não hiperparâmetros.

---

## 7. Output e Interpretação

### 7.1 Terminal

5 blocos: parâmetros calibrados, previsões da fase de grupos, top 20 favoritos ao título, probabilidade de classificação por grupo, apostas recomendadas (EV-optimal).

**Leitura de uma previsão:**
```
Brazil 2x0 Scotland    [62%/25%/14%]   EV=3.4  [modal: 1x1]
```
- `2x0` = placar EV-optimal recomendado
- `[62%/25%/14%]` = P(home) / P(empate) / P(away)
- `EV=3.4` = valor esperado de pontos com essa aposta
- `[modal: 1x1]` = o modal seria diferente, EV-optimal escolheu 2x0

### 7.2 JSON

`bolao2026_results.json` com predictions, simulation_stats, group_bets, champion_bet, third_places, model_params, tournament_factors, scorer_results.

---

## 8. Forças do Modelo

### 8.1 Fundamentação teórica

Todos os componentes têm base em literatura acadêmica: Dixon-Coles (1997), Poisson bivariado (Maher 1982), blend bayesiano, time-decay exponencial, Monte Carlo.

### 8.2 Performance

Pipeline completo em ~6s. EV-optimal em ~20ms. Iteração rápida para testar hipóteses.

### 8.3 Múltiplas fontes complementares

DC (forma recente), Elo (força histórica), TM (qualidade individual). Quando convergem, alta confiança. Quando divergem, sinal de revisão.

### 8.4 EV-optimal matematicamente correto

Solução exata do problema de otimização (não heurística). Dados os parâmetros do modelo, não há aposta individual com maior EV.

### 8.5 Modularidade e configurabilidade

Todos os parâmetros em `config.json`. Features opcionais com toggles independentes. Interface Streamlit para calibração visual.

---

## 9. Fraquezas e Limitações

### 9.1 Brasil superestimado, Inglaterra subestimada

Os dois maiores erros vs. mercado:

| Time | Modelo | Mercado | Erro |
|---|---|---|---|
| **Brasil** | ~9.7% | ~7% | +2.7 pp |
| **Inglaterra** | ~4.3% | ~12.4% | -8.1 pp |

**Diagnóstico Brasil:** o DC vê o Brasil corretamente como 6º (α_DC = +0.586, compatível com 9V 6E 5D nos últimos 20 jogos). A inflação residual vem do Elo (1984, 5º — lag temporal) e TM (€854M, 5º — qualidade individual ≠ coletiva).

**Diagnóstico Inglaterra:** o DC a subestima fortemente (α_DC = +0.187, 17º) por resultados medianos em qualifiers/amistosos. Elo e TM corrigem parcialmente (α_final = +0.388, 6º) mas não o bastante. A Inglaterra superperforma em torneios curtos — fenômeno que nenhum dos 3 canais captura.

**Correções pendentes:** backtest formal dos pesos do blend; modelo de escalação quando convocações reais estiverem disponíveis.

### 9.2 Poisson subestima variância (zebras)

O Poisson assume Var = E, mas em torneios curtos a variância real é maior (pressão, arbitragem, jogo único). O modelo é ligeiramente exagerado na confiança dos favoritos.

### 9.3 Bracket do mata-mata simplificado

Pareamento sequencial dos 32 classificados, não respeitando a chave FIFA real (cross-bracket). Probabilidades condicionais de encontro entre times têm erro sistemático.

### 9.4 Otimização conjunta de classificação não implementada

O modelo otimiza cada placar isoladamente. Mas os placares induzem classificação (vale até 20 pts/grupo + 5 pts/3º). Otimização conjunta é problema combinatorial mais difícil — `optimal_group_bet()` serve como diagnóstico mas não otimiza os placares.

### 9.5 Bracket completo como árvore

O mata-mata é preenchido inteiro de uma vez. A otimização deveria considerar a árvore completa (quem avança em R32 determina quem joga em R16). Design doc em `design_optimal_full_bracket.md` (algoritmo DP, O(160) entradas). Implementação pendente.

### 9.6 Calibração empírica via backtest

O modelo foi validado contra a Copa 2022 usando dados de época (ELOs e Transfermarkt de novembro/2022, sem data leakage). O grid search completo (660 combinações de variáveis) revelou:

- A melhor configuração encontrada faz **201 pts** — praticamente empatando com o Baseline "Favorito 1x0" (202 pts) e perdendo para o Baseline "Favorito 2x1" (223 pts)
- **DC puro (100%) supera o blend** com ELO e TM na Copa 2022, sugerindo que os priors adicionam ruído para este torneio específico
- **Quality filter ON** ganha em média ~5 pts vs OFF
- **xi não é sensível**: variação entre 0.0003 e 0.005 muda menos de 3 pts em média
- **tm_scale log > sqrt** por margem pequena (+3.6 pts médios)
- **date_cutoff 2016 > 2018 > 2020**: mais dados históricos ajuda

**Limitação:** N=1 (apenas Copa 2022). A Copa 2022 teve resultados atípicos (Argentina vs Arábia Saudita, Marrocos nas semis). Otimizar demais para 2022 é overfitting. Os resultados indicam direção, não valores definitivos.

O backtest e o otimizador estão disponíveis na aba "Backtest & Otimização" do Streamlit e em `backtests/wc2022/`.

### 9.7 Limitações menores

- Expert adjustments: só `attack_mult`, não `defense_mult`
- Estimativas de TM para times pequenos são aproximações
- `xi = 0.001` não calibrado empiricamente (valor da literatura)

---

## 10. Roadmap de Melhorias

Organizado pelos deadlines do bolão (ver PRAZOS.md).

### 10.1 Pré-7/6 (Fase 1 — placares + campeão + artilheiro)

- **Modelo de artilheiro** — modelar P(jogador é artilheiro) usando convocações reais, gols/jogo por jogador, e minutos esperados na Copa. Arquivo de escalações em `escalacoes_copa_2026.md` (25 finalizadas, 23 pendentes até 2/6)
- **Aplicar calibração otimizada** — usar resultados do grid search 2022 como guia para os pesos do blend, xi, e demais variáveis
- **Backtest contra Copa 2018** — segundo ponto de validação para evitar overfitting ao 2022
- **Otimização conjunta da fase de grupos** — placar + classificação induzida + 3ºs como função objetivo única
- **Investigar placares conservadores** — o modelo aposta muitos 0x1 e 1x0 quando 2x1 ou 2x0 daria mais pontos. Pode ser problema no `ev_optimal_score`

### 10.2 Pós-27/6 (Fase 2 — bracket do mata-mata)

- **Aceitar pares reais do R32** — MC condicionado ao bracket real
- **MC com dados per-slot** — gravar quem avança e quais pares jogam por slot
- **DP bracket completo** — implementar `optimal_full_bracket()` conforme design doc
- **Recalibração pós-grupos** — recalibrar com resultados reais

### 10.3 Melhorias gerais (qualquer momento)

- **Bracket FIFA oficial** — cross-bracket correto no MC
- **Ativar defense_mult** nos expert adjustments

---

## 11. Apêndice Técnico

### 11.1 Estrutura de arquivos

```
bolao-2026/
├── bolao2026.py                    # Modelo principal (~93k)
├── config.json                     # Parâmetros editáveis (Calibration)
├── app.py                          # Frontend Streamlit (calibração, simulação, backtest)
├── results.csv                     # Dados históricos (~49k jogos internacionais)
├── bolao2026_results.json          # Output da última execução
├── escalacoes_copa_2026.md         # Escalações oficiais das 48 seleções
├── requirements.txt                # Dependências Python
│
├── backtests/
│   └── wc2022/                     # Backtest Copa 2022 (dados isolados de época)
│       ├── data/
│       │   ├── elo_2022.json       # ELOs de nov/2022 (eloratings.net)
│       │   └── tm_2022.json        # Transfermarkt de nov/2022
│       ├── run_backtest.py         # Backtest limpo (sem data leakage)
│       └── optimize.py             # Grid search de calibração (660 combinações)
│
├── scripts/
│   ├── update_elos.py              # Atualiza ELOs via eloratings.net
│   ├── update_elos_playwright.py   # Versão com Playwright (JS-heavy sites)
│   ├── update_data.py              # Atualiza results.csv
│   ├── backtest_2022.py            # Backtest antigo (DEPRECATED — usar backtests/wc2022/)
│   ├── diff_elos.py                # Compara ELOs entre versões
│   └── audit_dc_matches.py        # Exporta jogos usados no fitting
│
├── services/
│   ├── storage.py                  # Persistência de runs em JSON/SQLite
│   ├── diff.py                     # Diff entre runs
│   └── sanity.py                   # Validação de sanidade do output
│
├── test_bolao_points.py            # Testes de bolao_points
├── test_group_champion_bet.py      # Testes de optimal_group_bet e champion_bet
├── test_knockout_bet.py            # Testes de optimal_knockout_bet
├── test_third_places.py            # Testes de induced_third_places
├── test_pipeline_smoke.py          # Smoke test do pipeline
├── test_storage.py                 # Testes do storage service
│
├── manual_bolao_do_zap.pdf         # Manual oficial do bolão
├── bolao_regras_oficiais_v2.md     # Gabarito de regras (versão atual)
├── auditoria_bolao.md              # Auditoria código vs manual
├── auditoria_bolao_v2.md           # Auditoria manual v1 vs v2
├── design_optimal_full_bracket.md  # Design doc: DP para bracket completo
├── PRAZOS.md                       # Datas e deadlines
├── TODO.md                         # Tarefas pendentes
├── bolao2026_README.md             # README
├── CLAUDE_CODE_PROMPT.md           # Briefing para Claude Code
│
├── data/
│   └── elo_ratings_latest.csv      # ELOs atuais (~244 seleções)
│
├── elo_bot/                        # Bot de scraping de ELOs (local, não commitado)
│
├── runs/                           # Runs salvos (JSON)
│
└── Doc Modelo Bolão/
    ├── bolao2026_documentacao.md   # ESTE ARQUIVO
    └── bolao2026_apresentacao.html # Apresentação visual do modelo
```

### 11.2 Constantes — referência rápida

| Constante | Valor | Onde |
|---|---|---|
| `w_dc / w_elo / w_tm` | 0.45 / 0.30 / 0.25 | config.json |
| `xi` | 0.001 | config.json |
| `wc_host_adv` | 0.12 | config.json |
| `n_sims` | 50000 | config.json |
| `max_goals` | 8 | hardcoded |
| `date_cutoff` | 2022-01-01 | config.json |
| `dc_quality_filter.enabled` | true | config.json |
| `tournament_factor.enabled` | false | config.json |
| `squad_data.enabled` | false | config.json |
| `top_scorer_model.enabled` | false | config.json |

### 11.3 Complexidade computacional

| Etapa | Tempo |
|---|---|
| Load CSV + filtro | ~0.6s |
| Dixon-Coles MLE | ~1-2s |
| Blend + ajustes | <0.01s |
| Precache lambdas | ~0.5s |
| Monte Carlo (50k) | ~4s |
| EV-optimal (72 jogos) | ~0.02s |
| Scorer model (se ativo, 2-3 times) | ~5-6s |
| **Total (sem scorer)** | **~6s** |

### 11.4 Referências

- Dixon, M.J. & Coles, S.G. (1997). "Modelling association football scores and inefficiencies in the football betting market." *Applied Statistics, 46(2), 265-280.*
- Maher, M.J. (1982). "Modelling association football scores." *Statistica Neerlandica, 36, 109-118.*
- Pollard, R. & Pollard, G. (2005). "Long-term trends in home advantage." *Journal of Sports Sciences, 23, 337-350.*
- Karlis, D. & Ntzoufras, I. (2003). "Analysis of sports data by using bivariate Poisson models." *The Statistician, 52, 381-393.*

### 11.5 Glossário

| Sigla | Significado |
|---|---|
| DC | Dixon-Coles |
| MLE | Maximum Likelihood Estimation |
| EV | Expected Value (valor esperado) |
| TM | Transfermarkt |
| WC | World Cup |
| R32/R16/QF/SF | Fases do mata-mata |
| λ/μ | Taxas esperadas de gols (mandante/visitante) |
| τ/ρ | Correção Dixon-Coles / parâmetro da correção |
| xi (ξ) | Parâmetro de time-decay |
| pp | Pontos percentuais |
| xG | Expected Goals |

### 11.6 Decisões de design não-óbvias

**Poisson vs Negative Binomial:** Poisson é canônico para contagem de gols. NB exigiria calibração de parâmetro extra de dispersão sem evidência clara de necessidade.

**Time-decay exponencial vs linear/step:** exponencial é suave, entra direto na likelihood como peso, e respeita a intuição de envelhecimento gradual.

**Soma de ataques = 0:** garante identificabilidade. Sem restrição, α + c e β - c produzem as mesmas previsões.

**ρ fitado (não fixado):** o valor ótimo varia com o dataset. Seleções vs clubes têm ρ diferentes.

**Sqrt vs log para TM:** O backtest 2022 mostra log levemente superior (avg +3.6 pts). A decisão entre sqrt e log deve ser validada com mais backtests (2018).

**50k simulações:** erro padrão para p=10% é 0.13 pp (IC 95% = ±0.26 pp). Precisão suficiente sem custo excessivo.

**DC puro vs blend:** O grid search 2022 indica que DC puro (100%) supera o blend com ELO/TM naquele torneio. Isso pode ser artefato de N=1 — os priors ELO/TM podem agregar valor em média mas terem sido prejudiciais na Copa 2022 especificamente (resultados atípicos). Decisão pendente de backtest 2018.

### 11.7 Checklist de sanidade

1. Tempo de execução entre 5-10 segundos
2. Top 5 favoritos são seleções top de Elo
3. Cascata de fases monotonicamente decrescente
4. Probabilidades somam 100% por grupo
5. EV-optimal diverge do modal em ~20-30% dos jogos
6. Probabilidade de empate na faixa 25-35% para jogos equilibrados
7. JSON gerado e não-corrompido

### 11.8 Contatos

**Desenvolvedor:** Alberto Hamoui (albertohamoui@gmail.com)
**Stack:** Python 3.14, numpy, scipy, pandas, streamlit

---

**Fim do documento.**
