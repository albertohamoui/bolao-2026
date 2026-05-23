# BOLAO 2026 - Briefing para Claude Code

## CONTEXTO

Modelo estatistico para prever resultados da Copa do Mundo FIFA 2026 para o Bolao do Zap (bolaodozap.com). Exige placar exato de todos os jogos + campeao + artilheiro.

**Deadline Fase 1:** 7 de junho de 2026, 23h59 (placares dos 72 jogos de grupo + campeao + artilheiro)
**Deadline Fase 2:** apos 27 de junho (bracket completo do mata-mata)
**Copa:** 11/jun a 19/jul/2026 (EUA, Canada, Mexico)

## ARQUITETURA

```
[49k jogos historicos] --> [Dixon-Coles MLE com time-decay + quality filter]
                                        |
                              [Blend bayesiano: DC + Elo + Transfermarkt]
                              [Pesos a calibrar via backtest]
                                        |
                              [Parametros ataque/defesa por selecao]
                                        |
                              [Monte Carlo 50k simulacoes do torneio]
                                        |
                              [EV-optimal: placar que maximiza pontos do bolao]
```

Componentes:
- **Dixon-Coles:** ataque/defesa por selecao, correcao tau para placares baixos, time-decay
- **Blend bayesiano:** DC + Elo + Transfermarkt (pesos configuraveis, calibracao empirica pendente)
- **Monte Carlo:** 50k torneios completos (grupos + mata-mata + penaltis)
- **EV-optimal score:** maximiza valor esperado de pontos do bolao (nao o placar mais provavel)
- **Host advantage:** EUA/Mexico/Canada recebem boost nos 9 jogos em casa

## ESTRUTURA DE ARQUIVOS

```
bolao-2026/
├── bolao2026.py                    # Modelo principal (~93k)
├── config.json                     # Hiperparametros editaveis
├── app.py                          # Streamlit (calibracao, simulacao, backtest)
├── results.csv                     # 49k jogos internacionais
├── escalacoes_copa_2026.md         # Escalacoes oficiais das 48 selecoes
├── backtests/wc2022/               # Backtest Copa 2022 (dados isolados)
│   ├── data/elo_2022.json          # ELOs nov/2022
│   ├── data/tm_2022.json           # TM nov/2022
│   ├── run_backtest.py             # Backtest limpo
│   └── optimize.py                 # Grid search (660 combinacoes)
├── scripts/                        # Utilitarios (update elos, diffs, audits)
├── services/                       # Storage, diff, sanity
├── test_*.py                       # Testes (pontuacao, apostas, pipeline)
└── Doc Modelo Bolão/               # Documentacao tecnica completa
```

## ESTADO ATUAL E PROXIMOS PASSOS

### Feito:
- Motor de simulacao Dixon-Coles + blend + Monte Carlo funcionando
- Streamlit com calibracao, simulacao, backtest e historico
- Backtest limpo contra Copa 2022 (dados de epoca, sem data leakage)
- Grid search de calibracao (660 combinacoes) integrado ao Streamlit
- Escalacoes de 25 selecoes finalizadas, 23 pendentes
- Auditoria de vies confirmou modelo neutro (sem favoritismo a nenhum time)

### Pendente (ordem de prioridade):
1. **Aplicar calibracao otimizada** — grid search 2022 indica DC puro > blend; validar com backtest 2018
2. **Investigar placares conservadores** — modelo aposta muitos 0x1 quando 2x1 daria mais pontos
3. **Modelo de artilheiro** — P(jogador e artilheiro) usando escalacoes reais + gols/jogo + minutos esperados
4. **Completar escalacoes** — atualizar conforme selecoes anunciam (ate 2/jun)
5. **Bracket mata-mata otimizado** — DP para arvore completa (design doc pronto)

### Achados do backtest 2022:
- Melhor config: DC puro, xi=0.0003, quality filter ON, cutoff 2016 → 201 pts
- Baseline "Favorito 2x1" faz 223 pts — modelo precisa melhorar placares
- Quality filter ON ganha ~5 pts em media
- xi pouco sensivel (0.0003 a 0.005 muda <3 pts)
- log > sqrt para TM scale (+3.6 pts medios)

## PRINCIPIOS

1. **Modelo sem vies** — todos os 48 times tratados identicamente pelo codigo
2. **Calibracao empirica** — variaveis definidas por backtest, nao por intuicao
3. **Dados isolados por epoca** — backtest 2022 usa dados de 2022, nao de 2026
4. **Convergencia com mercado** — divergencias grandes indicam erro, nao insight
5. **Expert adjustments sao residuais** — so para fatores que dados nao capturam (lesoes, etc.)

## STACK

Python 3.14, numpy, scipy, pandas, streamlit. Performance: ~6s para pipeline completo.

## COMUNICACAO

- Brasileiro, portugues e ingles
- Explicacoes diretas, sem diplomatismo
- Background em financas/dados (credito estruturado)
- Entende estatistica/probabilidade, nao e programador profissional
- Nunca usar Wikipedia como fonte de dados
