# Design: `optimal_full_bracket`

**Data:** 2026-04-23
**Status:** Proposta de design — nao implementar ate aprovacao.

---

## 0. Esclarecimento sobre o bonus de campeao

O bonus de campeao (25 pts) vem da aba **Campeao**, com deadline 7/6 — ANTES da Copa comecar. O bracket (mata-mata) e preenchido APOS 27/6, com deadline separado. Sao apostas independentes com scoring independente.

O participante pode apostar Franca como campeao (aba Campeao, 7/6) e depois montar um bracket onde o Brasil vence a Final (aba Mata-Mata, 27/6+). Ambas as apostas sao avaliadas em separado:
- 25 pts se o campeao real = palpite da aba Campeao
- 10 pts se o time que venceu a Final real = time que venceu a Final no bracket

**Consequencia:** o bonus de campeao NAO e parte da funcao objetivo do bracket. O bracket otimiza apenas: pontos de placar (via `_POINTS_KNOCKOUT`) + pontos "time que avancou" (10 pts por acerto).

Se houver duvida sobre isso, confirmar antes de implementar. O restante deste design assume que o bonus de campeao e separado.

---

## (a) Funcao Objetivo

Para um bracket completo (31 jogos), o EV total e:

```
EV(bracket) = Σ_{g=1}^{31} [ EV_placar(g) + EV_avanco(g) ]
```

Onde:

- **EV_placar(g)** = E[ bolao_points(bet_score_g, actual_score_g, knockout=True) ]
  - Depende da distribuicao de placares reais no slot g (quem de fato joga ali)
  - NAO depende de quem o participante preve que joga ali

- **EV_avanco(g)** = 10 × P(bet_advance_g e o time que de fato avanca no slot g)
  - Depende de quem o participante aposta como avancando

### Observacao critica: placar e avanco sao parcialmente acoplados

O participante faz UM palpite por jogo: um placar (a × b). Se a > b, quem avanca e o time da esquerda do slot. Se a < b, o da direita. Se a = b, o participante escolhe quem passa nos penaltis.

Portanto, a decisao de avanco **restringe** o regime do placar:
- Apostar que o time da esquerda avanca → placar deve ter home vencendo OU empate
- Apostar que o da direita avanca → placar deve ter away vencendo OU empate

A funcao objetivo completa de cada jogo e:

```
EV_jogo(g, t, regime) =
    score_ev(g, regime) + 10 × p_advance(t, g)
```

Onde:
- `t` = time apostado para avancar do slot g
- `regime` ∈ {vitoria_home, vitoria_away, empate}
- `score_ev(g, regime)` = max_{score no regime} E[ bolao_points(score, actual_g) ]

E a restricao de consistencia e: `regime` deve ser compativel com `t`.

---

## (b) Incerteza dos Pares de R16+

No momento de preencher (apos 27/6):

| Fase | Pares | Conhecimento |
|------|-------|-------------|
| R32 | 16 jogos | **Conhecidos** (determinados pela classificacao real dos grupos) |
| R16 | 8 jogos | **Dependem do bracket do participante** — quem ele apostou que venceu em R32 |
| QF | 4 jogos | Dependem dos vencedores apostados de R16 |
| SF | 2 jogos | Dependem dos vencedores apostados de QF |
| Final | 1 jogo | Depende dos vencedores apostados de SF |

Os pares REAIS (que de fato vao jogar) sao desconhecidos para R16+. Mas as probabilidades podem ser estimadas pelo Monte Carlo.

### O que importa para a otimizacao

Para cada slot g, precisamos de duas informacoes do MC:

1. **p_advance(team, slot)** — probabilidade de que `team` seja o time que de fato avanca do slot g no torneio real.

2. **mixture_score_matrix(slot)** — distribuicao de placares reais no slot g, misturando todos os possiveis pares que poderiam jogar ali.

Ambas sao **propriedades da realidade** (nao do bracket do participante). O bracket do participante escolhe quem ELE acha que avanca, mas os pontos sao avaliados contra a realidade.

### Consequencia

O palpite do participante NAO afeta as probabilidades reais. Entao:
- `p_advance(t, g)` e `mixture_score_matrix(g)` podem ser pre-computados do MC
- A otimizacao do bracket usa esses valores como constantes

Isso simplifica drasticamente o problema — nao ha "ramificacao" da otimizacao condicionada a pares hipoteticos.

---

## (c) Algoritmo: DP em Arvore

### Estrutura

O bracket e uma arvore binaria completa:

```
                          Final
                     /            \
                  SF1              SF2
                /    \           /    \
             QF1     QF2      QF3     QF4
            / \     / \      / \     / \
          R16  R16 R16 R16 R16  R16 R16 R16
          /\   /\  /\  /\  /\  /\  /\  /\
        R32 ... (16 jogos de R32, 32 times)
```

Cada no interno e um slot de jogo. Cada folha e um time de R32.

### Definicao da DP

Para cada slot g na arvore e cada time t alcancavel a partir da subarvore de g:

```
DP[g][t] = maximo EV total da subarvore de g,
           dado que apostamos que t avanca do slot g
```

### Caso base: R32

Slot g com times conhecidos A (esquerda) e B (direita):

```
DP[g][A] = score_ev_home(g) + 10 × p_advance(A, g)
DP[g][B] = score_ev_away(g) + 10 × p_advance(B, g)
```

Onde:
- `score_ev_home(g)` = max(ev dos placares com home vencendo, ev dos empates)
- `score_ev_away(g)` = max(ev dos placares com away vencendo, ev dos empates)

Para R32, a score_matrix vem de `model.predict_match(A, B)` (par conhecido).

### Caso recursivo: slot interno

Slot g com filhos g_left e g_right. Time t pode vir do filho esquerdo ou direito:

```
Se t ∈ candidates(g_left):
    DP[g][t] = DP[g_left][t]                       # custo de mandar t pela esquerda
             + max_u { DP[g_right][u] }             # melhor escolha na direita
             + score_ev_home(g)                     # placar (t esta na esquerda = home)
             + 10 × p_advance(t, g)                 # bonus avanco

Se t ∈ candidates(g_right):
    DP[g][t] = max_u { DP[g_left][u] }              # melhor escolha na esquerda
             + DP[g_right][t]                       # custo de mandar t pela direita
             + score_ev_away(g)                     # placar (t esta na direita = away)
             + 10 × p_advance(t, g)                 # bonus avanco
```

### Solucao final

```
optimal_ev = max_t { DP[Final][t] }
optimal_champion = argmax_t { DP[Final][t] }
```

### Reconstrucao do bracket

Backtrack da raiz para as folhas:
1. Na Final, o time otimo define o campeao do bracket.
2. Descer: ele veio do filho esquerdo ou direito? Buscar qual subarvore.
3. No filho de onde veio, repetir. No outro filho, pegar o argmax do DP.
4. Recursivamente ate R32.

Para cada slot, o regime de placar (vitoria ou empate) e o placar otimo sao determinados durante o backtrack.

### Pseudocodigo

```python
def optimal_full_bracket(
    r32_matchups: List[Tuple[str, str]],  # 16 pares de R32 (conhecidos)
    p_advance: Dict[Tuple[str, int], float],
        # p_advance[(team, slot_id)] = P(team avanca do slot real)
    mixture_matrices: Dict[int, np.ndarray],
        # mixture_matrices[slot_id] = score_matrix 8x8 (mistura ponderada)
) -> Dict[str, Any]:

    # 1. Construir arvore do bracket (32 folhas, 31 nos internos)
    tree = build_bracket_tree(r32_matchups)

    # 2. Pre-computar score_ev por slot e regime
    for slot in tree.all_slots():
        M = mixture_matrices[slot.id]
        slot.score_ev_home = max(
            best_ev_regime(M, "home_wins"),
            best_ev_regime(M, "draw"),
        )
        slot.score_ev_away = max(
            best_ev_regime(M, "away_wins"),
            best_ev_regime(M, "draw"),
        )

    # 3. DP bottom-up
    for slot in tree.bottom_up():
        if slot.is_r32():
            A, B = slot.teams
            slot.dp = {
                A: slot.score_ev_home + 10 * p_advance[(A, slot.id)],
                B: slot.score_ev_away + 10 * p_advance[(B, slot.id)],
            }
        else:
            L, R = slot.left, slot.right
            max_right = max(R.dp.values())
            max_left = max(L.dp.values())
            slot.dp = {}
            for t in L.dp:
                slot.dp[t] = (L.dp[t] + max_right
                              + slot.score_ev_home
                              + 10 * p_advance.get((t, slot.id), 0))
            for t in R.dp:
                slot.dp[t] = (max_left + R.dp[t]
                              + slot.score_ev_away
                              + 10 * p_advance.get((t, slot.id), 0))

    # 4. Backtrack para reconstruir bracket
    bracket = backtrack(tree)
    return bracket
```

---

## (d) Inputs Necessarios e Modificacoes no MC

### Input 1: p_advance(team, slot)

**Definicao:** probabilidade de que `team` seja o time real que avanca do slot g.

**O que o MC grava hoje:**
- `team_stats[t]["r32"]`, `["r16"]`, ..., `["champion"]` — probabilidade MARGINAL de t alcancar cada fase.
- Isso e insuficiente: "Brazil alcanca QF" nao diz em QUAL dos 4 slots de QF ele esta.

**Modificacao necessaria no MC:**

Dentro de `simulate_tournament`, o MC ja percorre os jogos do mata-mata slot por slot (linhas 1064-1082). So falta registrar, por slot, quem avancou:

```python
# Novo: no inicio de simulate_tournament ou run_simulations
slot_advance_counts = {
    round_name: [Counter() for _ in range(n_games)]
    for round_name, n_games in [
        ("R32", 16), ("R16", 8), ("QF", 4), ("SF", 2), ("Final", 1)
    ]
}

# Dentro do loop de simulacao, apos determinar o vencedor de cada jogo:
for game_idx, (h, a, winner) in enumerate(rounds_results[round_name]):
    slot_advance_counts[round_name][game_idx][winner] += 1

# Apos n_sims, normalizar:
p_advance = {}
for round_name, slots in slot_advance_counts.items():
    for slot_idx, counter in enumerate(slots):
        for team, count in counter.items():
            p_advance[(team, round_name, slot_idx)] = count / n_sims
```

**Custo:** O(31) por simulacao (uma operacao por jogo do mata-mata). Negligivel.

### Input 2: mixture_score_matrix(slot)

**Definicao:** para cada slot g, a distribuicao de placares reais, misturando todos os pares possiveis.

**Opcao A — Contagem de pares no MC (recomendada):**

Registrar quais times jogaram em cada slot:

```python
slot_matchup_counts = {
    round_name: [Counter() for _ in range(n_games)]
    ...
}
# Dentro do loop:
slot_matchup_counts[round_name][game_idx][(h, a)] += 1
```

Apos o MC, para cada slot com pares {(A1,B1): n1, (A2,B2): n2, ...}:

```python
mixture = np.zeros((8, 8))
for (A, B), count in slot_matchup_counts[round][slot].items():
    weight = count / n_sims
    sm = model.predict_match(A, B)  # predict_match ja existe
    mixture += weight * sm
```

**Custo do pos-processamento:** para cada slot, iterar sobre pares unicos (tipicamente 2-50 pares por slot) e chamar `predict_match` (O(64) cada). Total: 31 slots × ~20 pares × 64 ≈ 40k operacoes. Desprezivel.

**Opcao B — Aproximacao pelo par mais provavel:**

Usar apenas o par (A, B) com maior frequencia em cada slot. Score_matrix = `predict_match(A, B)`. Simples, rapido, bom o bastante na maioria dos slots (em R32, exato; em R16, o par mais provavel tipicamente tem >30% de frequencia).

**Recomendacao:** Opcao A (exata). E barata e elimina erro de aproximacao.

### Nota sobre o bracket do MC vs bracket real

O MC atual (`simulate_tournament`) monta o bracket por emparelhamento consecutivo dos classificados:

```python
r32_teams = [q[1] for q in qualified]
# Pareamento: [0]v[1], [2]v[3], ..., [30]v[31]
```

Isso pode NAO corresponder ao bracket oficial da FIFA 2026 (que tem uma chave especifica). Para que `p_advance` e `mixture_score_matrix` sejam consistentes com a realidade:

1. **Pre-27/6:** o MC usa o emparelhamento aproximado que esta no codigo. Os valores de `p_advance` sao estimativas. Isso e suficiente para planejamento.

2. **Pos-27/6 (quando temos o bracket real):** modificar o MC para aceitar os matchups reais de R32 como input, em vez de derivar dos grupos simulados. Rodar um MC "condicionado" que so simula o mata-mata com os pares reais.

Essa modificacao e simples: adicionar um parametro `r32_matchups` a `run_simulations` (ou uma funcao separada `simulate_knockout_only`).

---

## (e) Complexidade Computacional

### DP

| Fase | Slots | Candidatos por slot | Entradas DP |
|------|------:|--------------------:|------------:|
| R32 | 16 | 2 | 32 |
| R16 | 8 | 4 | 32 |
| QF | 4 | 8 | 32 |
| SF | 2 | 16 | 32 |
| Final | 1 | 32 | 32 |
| **Total** | **31** | | **160** |

Cada entrada: O(1) (soma + lookup em dict).
**Total DP: O(160) — microsegundos.**

### Pre-computacao de score_ev por slot

31 slots × `ev_optimal_score` (8×8×8×8 = 4096 operacoes) = 127k operacoes.
**~10ms.**

### Pre-computacao de mixture_score_matrix

31 slots × ~20 pares unicos × `predict_match` (O(64)) × pesos = ~40k operacoes.
**~5ms.**

### MC com slot tracking

Sobrecusto sobre o MC atual: 31 incrementos de contador por simulacao.
Para 50k sims: 1.55M incrementos. **~100ms extra** (negligivel vs os ~6s do MC).

### Total

| Etapa | Tempo estimado |
|-------|---------------:|
| MC (com slot tracking) | ~6s (existente) + ~100ms |
| Mixture score matrices | ~5ms |
| Score EV por slot | ~10ms |
| DP | < 1ms |
| Backtrack + reconstrucao | < 1ms |
| **Total (excluindo MC)** | **< 20ms** |

**Muito dentro do orcamento de ~1s.** O gargalo e o MC, que ja existe e roda em ~6s.

---

## Resumo da Arquitetura

```
              [MC com slot tracking]
                      |
           +----------+----------+
           |                     |
    p_advance(t, slot)    slot_matchup_counts
           |                     |
           |              mixture_score_matrix(slot)
           |                     |
           |              score_ev per regime
           |                     |
           +----------+----------+
                      |
              [DP bottom-up na arvore]
                      |
              [Backtrack top-down]
                      |
              bracket otimo completo
              (31 placares + 31 avancos)
```

### Interface proposta

```python
def optimal_full_bracket(
    r32_matchups: List[Tuple[str, str]],
    model: DixonColesModel,
    p_advance: Dict[Tuple[str, str, int], float],
    slot_matchup_counts: Dict[str, List[Counter]],
) -> Dict[str, Any]:
    """
    Retorna:
    {
        "bracket": [
            {"round": "R32", "slot": 0, "home": "...", "away": "...",
             "score": (2, 1), "advance": "...", "regime": "vitoria",
             "ev_score": 4.2, "ev_advance": 7.1},
            ...  # 31 entradas
        ],
        "total_ev": float,
        "champion_bracket": str,  # quem vence a Final no bracket
    }
    """
```

### Dependencias de implementacao

1. **Modificar `run_simulations`** para gravar `slot_advance_counts` e `slot_matchup_counts`.
2. **Implementar `build_bracket_tree`** — estrutura de arvore para a DP.
3. **Implementar `optimal_full_bracket`** — DP + backtrack.
4. **Implementar (pos-27/6) `simulate_knockout_only`** — MC condicionado ao bracket real.

Os itens 1-3 podem ser implementados ja. O item 4 so e necessario apos 27/6 para refinar `p_advance` com os matchups reais.

---

## Questoes Abertas para Confirmacao

1. **Bonus campeao e separado do bracket?** Este design assume que sim (apostas com deadlines diferentes). Se nao, adicionar `+ 25 × p_advance(t, Final)` na DP do no Final — mudanca trivial.

2. **Bracket do MC usa chave oficial FIFA?** O codigo atual usa emparelhamento consecutivo, que pode divergir da chave real. Para pre-27/6 (planejamento), aceitavel. Para pos-27/6 (otimizacao real), precisa dos matchups reais.

3. **Interacao com palpite de campeao ja feito:** se o participante apostou Franca como campeao (antes de 7/6), vale a pena enviesar o bracket para ter Franca na Final? Matematicamente nao — o bonus de campeao ja foi apostado e nao muda. O bracket so otimiza placar + avanco. Mas psicologicamente o participante pode preferir consistencia. Decisao do usuario.
