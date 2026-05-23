# BOLAO 2026 - Modelo de Previsao da Copa do Mundo FIFA 2026

## Arquitetura

**Dixon-Coles + Bayesian Update + Monte Carlo Ensemble**

### O que e o modelo Dixon-Coles?

Uma evolucao do modelo de Poisson bivariado classico, proposta por Mark Dixon e Stuart Coles em 1997. Ele:

1. Estima parametros de **ataque** e **defesa** para cada selecao
2. Aplica uma **correcao (tau)** para placares baixos (0-0, 1-0, 0-1, 1-1), que o Poisson puro subestima
3. Usa **time-decay** para dar mais peso a jogos recentes
4. Gera uma **distribuicao completa de probabilidades** para cada placar possivel

### Pipeline completo

```
[Dados historicos] -> [Dixon-Coles calibrado] -> [Previsoes por jogo]
                                                         |
[Elo Ratings] -----> [Power Rating] -----> [Lambdas] --->|
                                                         |
[Ajuste Expert] --> [Multiplicadores] ------------------>|
                                                         v
                                              [Monte Carlo 50k sims]
                                                         |
                                                         v
                                              [Probabilidades completas]
                                              [Placares recomendados]
                                              [Quem passa de fase]
```

## Como rodar

### Requisitos
```bash
pip install numpy scipy pandas
```

### Passo 1: Baixar dados historicos
```bash
python bolao2026.py --download
```
Isso baixa ~47.000 resultados de jogos internacionais desde 1872.

### Passo 2: Rodar o modelo
```bash
python bolao2026.py
```

O modelo:
1. Carrega os dados historicos
2. Calibra o Dixon-Coles com jogos desde 2022
3. Gera previsoes para todos os 72 jogos da fase de grupos
4. Roda 50.000 simulacoes Monte Carlo
5. Exporta resultados em JSON

### Passo 3: Ajuste Expert (opcional)
Edite o campo `expert_adjustments` no arquivo `config.json`:

```json
{
    "expert_adjustments": {
        "Brazil": {"attack_mult": 0.95},
        "Argentina": {"attack_mult": 1.05}
    }
}
```

O `config.json` e criado automaticamente na primeira execucao com valores default. Todos os parametros do modelo (pesos do blend, host advantage, numero de simulacoes, etc.) sao editaveis nesse arquivo.

## Output

O modelo gera:
- **Placar recomendado** para cada jogo
- **Probabilidades** de vitoria/empate/derrota
- **xG** (gols esperados) por selecao
- **Distribuicao completa** de placares (0x0 ate 7x7)
- **Probabilidade de classificacao** por grupo
- **Probabilidade de titulo** por selecao

## Status atual

| Feature | Status | Nota |
|---|---|---|
| Filtro qualidade DC | **Ativo** | Pesa menos jogos entre adversarios desiguais |
| Backtest Copa 2022 | **Ativo** | Dados de epoca (ELOs/TM nov/2022), sem data leakage |
| Grid search otimizador | **Ativo** | 660 combinacoes de variaveis via Streamlit |
| Escalacoes Copa 2026 | **Parcial** | 25 finalizadas, 23 pendentes (deadline FIFA: 2/jun) |
| Tournament Factor V2 | Desligado | Impacto empirico marginal |
| Modelo de escalacao | Desligado | Ativar apos convocacoes completas |
| Modelo de artilheiro | Pendente | Proximo passo apos calibracao |

## Backtest e Otimizacao

O modelo inclui um sistema de backtest limpo contra a Copa 2022:

- **Dados isolados** em `backtests/wc2022/data/` (ELOs e Transfermarkt de nov/2022)
- **Grid search** testa 660 combinacoes de variaveis e encontra a melhor
- **Disponivel via Streamlit** (aba "Backtest & Otimizacao") ou CLI

```bash
# Backtest unico com defaults
python3 backtests/wc2022/run_backtest.py

# Grid search completo
python3 backtests/wc2022/optimize.py

# Grid search rapido (~30 combos)
python3 backtests/wc2022/optimize.py --quick
```

## Escalacoes

Arquivo `escalacoes_copa_2026.md` com as escalacoes oficiais de todas as 48 selecoes, organizado por grupo. Fontes: CNN Brasil, O Globo, BBC, Sky Sports, FA inglesa, NFF norueguesa — cross-checked entre multiplas fontes.

## Interface Streamlit

```bash
pip install -r requirements.txt
streamlit run app.py
```

Abas disponiveis:
- **Calibracao** — ajustar hiperparametros (pesos do blend, xi, host advantage, etc.)
- **Rodar Simulacao** — executar pipeline completo com Monte Carlo
- **Backtest & Otimizacao** — backtest contra Copa 2022 + grid search de calibracao
- **Historico** — comparar runs salvos

Ver documentacao completa em `Doc Modelo Bolão/bolao2026_documentacao.md`.
