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

## Status atual (Sprint 3.5)

| Feature | Status | Default | Nota |
|---|---|---|---|
| Elo ratings corrigidos | **Sempre ativo** | — | Atualizados em 23/abr/2026 (eloratings.net) |
| Bug fix time-decay | **Sempre ativo** | — | `_log_likelihood` agora usa weights corretamente |
| Filtro qualidade DC | **Ativo** | `enabled: true` | Pesa menos jogos entre adversarios desiguais |
| Tournament Factor V2 | Desligado | `enabled: false` | Impacto empirico marginal (<0.2pp). Codigo preservado. |
| Modelo de escalacao | Desligado | `enabled: false` | Ativar apos convocacoes FIFA (~01/jun/2026) |
| Modelo de artilheiro | Desligado | `enabled: false` | Ativar apos preencher player_stats no config.json |

## Como ativar features opcionais

Todas as features sao controladas via `config.json`. Exemplo para ativar o modelo de escalacao:

```json
{
  "squad_data": {
    "enabled": true,
    "weight": 0.5,
    "use_top_11": false,
    "convocated_squads": {
      "Brazil": [
        {"name": "Vinicius Jr.", "value_eur_m": 180, "position": "ATK"},
        ...
      ]
    }
  }
}
```

Para o modelo de artilheiro, preencher `top_scorer_model.player_stats` com dados por jogador.

Ver documentacao completa em `Doc Modelo Bolão/bolao2026_documentacao.md` (secoes §3.7, §3.8, §3.9).

## Como atualizar Elo ratings

```bash
# Criar arquivo com novos valores (JSON simples {"Team": valor, ...})
python scripts/diff_elos.py novos_elos.json
# Revisar diff, confirmar, e replicar em DEFAULT_ELO_RATINGS no bolao2026.py
```

## Interface de calibracao (Streamlit)

```bash
pip install streamlit
streamlit run app.py
```

Permite ajustar todos os hiperparametros via interface grafica, com presets "Modo Legacy" e "Modo Producao Atual" para comparacao rapida. Ver documentacao §6.5.
