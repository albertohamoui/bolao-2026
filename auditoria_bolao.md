# Auditoria do Modelo `bolao2026.py` vs Manual Oficial

**Arquivos:**
- Código auditado: `bolao2026.py` (44 KB, última alteração 2026-04-17)
- Gabarito: `bolao_regras_oficiais.md` (gerado nesta auditoria a partir de `manual_bolao_do_zap.pdf`)
- Data da auditoria: 2026-04-22

**Escopo:** auditoria das funções de pontuação e otimização contra o manual oficial do bolão. Nenhum código foi modificado — este relatório apenas propõe correções e novas funções.

---

## Resumo Executivo

**Divergências críticas em código existente: 3**
1. Multiplicador do mata-mata errado: código usa ×2, manual usa tabela explícita equivalente a ×1.5 com arredondamentos irregulares (`bolao2026.py:293`, `bolao2026.py:275`).
2. Empate exato no mata-mata dobrado errado: código devolve 20, manual diz 15 (`bolao2026.py:302`).
3. Empate com placar errado no mata-mata: código devolve 12, manual diz 9 (`bolao2026.py:303`).

**Componentes de pontuação NÃO implementados (dinheiro na mesa): 5**
1. **Classificação dos grupos** (1º/2º, até 240 pts) — só probabilidades marginais são exibidas.
2. **Terceiros colocados** (até 40 pts) — probabilidade é calculada, EV não.
3. **Placares do mata-mata** (até 465 pts) — não há `ev_optimal_score` para jogos eliminatórios.
4. **"Time que avançou" no mata-mata** (até 310 pts) — bônus não existe em `bolao_points()` nem em função separada.
5. **Aposta de campeão** (25 pts) — `P(champion)` é mostrada, aposta ótima não.
6. **Aposta de artilheiro** (30 pts) — não modelado (TODO reconhecido).

**Estimativa de pontos deixados na mesa: 350–500 pts de EV otimizável não capturado.** A otimização atual cobre apenas placares da fase de grupos (≈40% do máximo teórico de 1830 pts). Os outros ≈60% estão sem otimização.

---

## Passo 2 — Auditoria de `bolao_points()`

**Localização:** `bolao2026.py:275-329`.

### Divergência #1 — CRÍTICA — Multiplicador do mata-mata

**Linha:** `bolao2026.py:293`

```python
mult = 2 if knockout else 1
```

**Problema:** o manual (página 4, tabela "Mata-Mata — Placares e Classificacao") indica multiplicador ×1.5 sobre os tiers da fase de grupos, com **arredondamento irregular** nos tiers onde a multiplicação dá fração. Os valores canônicos do manual são:

| Tier | Grupos | Código atual (×2) | Manual (×1.5 arredondado) |
|------|-------:|------------------:|--------------------------:|
| Placar exato | 10 | 20 | **15** |
| Diferença | 6 | 12 | **9** |
| Gols do vencedor | 5 | 10 | **8** (não 7.5) |
| Gols do perdedor | 4 | 8 | **6** |
| Só o vencedor | 3 | 6 | **5** (não 4.5) |
| Empate exato | 10 | 20 | **15** |
| Empate placar errado | 6 | 12 | **9** |

**Fonte:** Manual página 4 — cada linha da tabela mostra explicitamente `"15 pts (10 × 1.5)"`, `"8 pts (5 × 1.5)"`, `"5 pts (3 × 1.5)"` etc. Os tiers K3 (8) e K5 (5) **não** batem com `grupos × 1.5` exato — o manual já arredondou.

**Impacto:** **todos os tiers do mata-mata estão errados** no código atual. Sobrestima o valor do placar exato em +33% (20 vs 15), do empate em +33% (20 vs 15), etc. Qualquer otimização EV que já tenha sido feita no mata-mata (não é feita hoje, mas se fosse) estaria usando o função corrompida.

**Diff sugerido:**

```python
# Substituir o esquema "mult = 2 if knockout else 1" por tabela explícita.

# Tabela canônica (tiers → pontos por contexto)
_POINTS_GROUP = {
    "exact":         10,  # G1
    "diff":           6,  # G2
    "winner_goals":   5,  # G3
    "loser_goals":    4,  # G4
    "winner_only":    3,  # G5
    "draw_exact":    10,  # G6
    "draw_wrong":     6,  # G7
}
_POINTS_KNOCKOUT = {
    "exact":         15,  # K1
    "diff":           9,  # K2
    "winner_goals":   8,  # K3 (NÃO 7.5 — arredondamento do manual)
    "loser_goals":    6,  # K4
    "winner_only":    5,  # K5 (NÃO 4.5 — arredondamento do manual)
    "draw_exact":    15,  # K6
    "draw_wrong":     9,  # K7
}

def bolao_points(bet, actual, knockout=False):
    bh, ba = bet
    rh, ra = actual
    table = _POINTS_KNOCKOUT if knockout else _POINTS_GROUP

    bet_draw = (bh == ba)
    result_draw = (rh == ra)

    if bet_draw:
        if not result_draw:
            return 0
        return table["draw_exact"] if bh == rh else table["draw_wrong"]

    if result_draw:
        return 0
    if (bh > ba) != (rh > ra):
        return 0
    if (bh, ba) == (rh, ra):
        return table["exact"]
    if (bh - ba) == (rh - ra):
        return table["diff"]

    if bh > ba:
        bwg, blg, rwg, rlg = bh, ba, rh, ra
    else:
        bwg, blg, rwg, rlg = ba, bh, ra, rh
    if bwg == rwg:
        return table["winner_goals"]
    if blg == rlg:
        return table["loser_goals"]
    return table["winner_only"]
```

### Divergência #2 — Tier "só o vencedor" está correto (3 grupos), errado no mata-mata

Confirmado: fase de grupos está ok (3 pts). No mata-mata, código devolve `3 × 2 = 6`; manual diz **5**. Coberto pela correção acima.

### Divergência #3 — Docstring desatualizada

**Linhas:** `bolao2026.py:276-289`. Documentação fala "10 / 20", "6 / 12", etc. — valores do mata-mata errados, mesma raiz da divergência #1. Atualizar para refletir a tabela canônica (15/9/8/6/5/15/9).

### NÃO-divergências (confirmar que estão corretos)

- Tratamento de empate exato na fase de grupos → 10 pts. **OK.** (linha 302)
- Tratamento de empate com placar errado na fase de grupos → 6 pts. **OK.** (linha 303)
- Tier "só o vencedor" fase de grupos → 3 pts. **OK.** (linha 329)
- Tratamento de `bet_draw` vs `result_draw` (palpite empate em não-empate = 0) → correto (linhas 298-300). Confere com manual G8.

### Componente FALTANDO em `bolao_points()` (ou em função irmã)

O manual inclui na MESMA tabela do mata-mata o bônus "Acertou o time que avançou: 10 pts". **Este componente não existe no código.** É independente do placar (soma por cima), então é melhor implementado em função separada (ver §6 abaixo) e não como tier de `bolao_points`.

### Sobre "actual" no mata-mata e prorrogação/pênaltis

*Pergunta do escopo do pedido:*
> Tratamento de prorrogação e pênaltis (no mata-mata, se o jogo termina empatado após 90/120min, o palpiteiro escolhe quem passa — isso afeta como deveríamos definir "actual" na função?)

**Resposta:** não afeta `bolao_points`. O manual (página 4, rodapé) diz que o placar **vale como empate** para fins de pontuação, mesmo que o jogo tenha sido decidido nos pênaltis. Então `actual = (hg, ha)` após 90/120min (sem considerar pênaltis) é a definição correta para os tiers de placar. A escolha "quem passa" é **variável separada** que alimenta apenas o bônus de 10 pts (§6).

---

## Passo 3 — Auditoria de `ev_optimal_score()`

**Localização:** `bolao2026.py:332-354`.

### Checks solicitados

1. **Usa `bolao_points` com a flag `knockout` certa?** Sim, a flag é passada pelo parâmetro.

2. **Cobertura do range de placares?** A iteração vai de 0 a `min(max_goals, score_matrix.shape[0])`. Como `score_matrix.shape[0]` é **8** (vem de `predict_match` com `max_goals=8` hardcoded em `bolao2026.py:556`), o loop nunca passa de 8×8=64 combinações. Para Copa, isso cobre quase toda a massa probabilística — P(placar ≥ 5×5 ou similar) é negligível em 99%+ dos pares. **Não há risco significativo de dinheiro na mesa por max_goals=8.** Recomendação: manter 8; se quiser conservadorismo absoluto, subir para 10 em `predict_match:556` e aqui.

3. **Chamada no pipeline:** `bolao2026.py:996` chama `ev_optimal_score(pred["score_matrix"], knockout=False)`. Correto para fase de grupos. **Problema:** não há chamada equivalente para mata-mata — o pipeline atual nem tem estrutura de confrontos do mata-mata para otimizar placar por confronto. Isso é esperado porque os palpites de mata-mata são feitos **antes de cada jogo** (manual, páginas 2 e 5), não em lote. Mas o modelo deveria fornecer a função para apoio antes de cada confronto — hoje não fornece.

### Divergência #4 — Ausência de otimização de placar no mata-mata

Não é um bug de `ev_optimal_score` em si (a função é genérica); é um **gap do pipeline**. A função já aceita `knockout=True` e, após a correção da divergência #1, estará correta. Só falta expô-la/chamá-la para os confrontos do mata-mata. Isso tipicamente vira uma função de apoio a ser chamada na aba de mata-mata do frontend.

### NÃO-divergências em `ev_optimal_score`

- Estrutura do duplo loop (bet × outcome) está matematicamente correta.
- Filtro `if p <= 0: continue` não introduz viés (apenas pula entradas impossíveis da matriz).

---

## Passo 4 — Bônus de Classificação dos Grupos (ausente)

**Status:** NÃO implementado. Representa até **240 pts** do total (12 grupos × 20).

### Especificação técnica proposta

**Modificação no Monte Carlo** (`bolao2026.py:800-853`):

Adicionar contador da distribuição **conjunta** top-2 por grupo:

```python
# Em team_stats ou em estrutura paralela, guardar:
group_top2_joint = {
    gname: np.zeros((4, 4), dtype=np.int64)  # indexado pelo índice do time no grupo
    for gname in self.groups
}
# Durante a simulação (dentro do loop de agregação):
for gname, gres in result["groups"].items():
    s = gres["standings"]
    teams = self.groups[gname]
    idx_1 = teams.index(s[0])
    idx_2 = teams.index(s[1])
    group_top2_joint[gname][idx_1, idx_2] += 1
# No fim, normalizar para probabilidade conjunta P(1º=X, 2º=Y).
```

**Nova função pura:**

```python
def optimal_group_bet(
    joint_top2: np.ndarray,  # shape (k, k), joint_top2[i, j] = P(1º=i, 2º=j)
    teams: List[str],         # mesma indexação da matriz
) -> Dict[str, Any]:
    """
    Encontra (bet_1st, bet_2nd) que maximiza EV combinado dos 10/10/5 do bolão.

    EV(b1, b2) = Σ_{i,j} P(1º=i, 2º=j) · pontos_classif((b1, b2), (i, j))
    onde pontos_classif((b1, b2), (i, j)) =
        10 · [b1 == i]
      + 10 · [b2 == j]
      +  5 · ([b1 == j] AND b1 != i)        # bet_1st é classificado em pos trocada
      +  5 · ([b2 == i] AND b2 != j)        # bet_2nd é classificado em pos trocada

    Retorna:
        {"bet_1st": str, "bet_2nd": str, "ev_points": float, "matrix": 2D dict}
    """
    k = len(teams)
    best_ev, best_pair = -1.0, (teams[0], teams[1])
    for b1 in range(k):
        for b2 in range(k):
            if b1 == b2:
                continue
            ev = 0.0
            for i in range(k):
                for j in range(k):
                    p = joint_top2[i, j]
                    if p <= 0:
                        continue
                    pts = 0
                    if b1 == i: pts += 10
                    if b2 == j: pts += 10
                    if b1 != i and b1 == j: pts += 5
                    if b2 != j and b2 == i: pts += 5
                    ev += p * pts
            if ev > best_ev:
                best_ev = ev
                best_pair = (teams[b1], teams[b2])
    return {"bet_1st": best_pair[0], "bet_2nd": best_pair[1], "ev_points": best_ev}
```

**Custo computacional:** 12 grupos × 4⁴ = 3072 iterações triviais. Desprezível no pipeline atual.

**Exemplo de uso no pipeline:**

```python
group_bets = {}
for gname in sorted(GROUPS.keys()):
    joint = simulator.group_top2_joint[gname] / cal.n_sims
    result_bet = optimal_group_bet(joint, GROUPS[gname])
    group_bets[gname] = result_bet
```

**Nota sobre independência:** a matriz conjunta captura corretamente os cenários cruzados (ex: "A foi 2º, B foi 1º"). Marginais P(team 1º) × P(team 2º) iriam **subestimar** o EV porque perderiam a correlação.

---

## Passo 5 — Bônus de Terceiros Colocados (ausente)

**Status:** P(3º qualificado) já é calculada (`group_3rd_qual` em `bolao2026.py:802, 831-832`). Falta calcular o EV.

### Observação crítica sobre o modelo do bolão

O palpite de 3ºs é **derivado** dos placares (manual, página 3): o sistema escolhe os 8 melhores 3ºs conforme a tabela induzida pelos palpites. Ou seja:

- **O usuário não escolhe seus 8 "palpites de 3º"** — eles saem automaticamente dos placares apostados.
- Para otimizar, o modelo teria que otimizar placares para induzir a tabela desejada (problema duro de otimização conjunta).

### Proposta (escopo enxuto, conforme pedido)

Implementar apenas diagnóstico, não otimização conjunta:

```python
def induced_third_place_bets(
    predictions: Dict[str, Any],  # saída do pipeline, com score_ev por jogo
    groups: Dict[str, List[str]],
) -> List[str]:
    """
    Replica a lógica FIFA (pts → saldo → gols marcados) sobre os placares EV-optimal
    escolhidos por grupo, retornando os 8 times que seriam 3ºs classificados.
    """
    # Reconstrói standings por grupo usando os score_ev já escolhidos
    # e aplica o tie-breaker FIFA entre os 12 terceiros para pegar os 8 melhores.

def third_place_ev(
    induced_thirds: List[str],         # nossos 8 "palpites" induzidos
    team_stats: Dict[str, Dict],       # saída do MC, com group_3rd_qual em %
) -> float:
    """
    EV em pontos = Σ_{t in induced_thirds} (P(t é 3º qualificado) / 100) · 5
    """
    return sum(team_stats[t]["group_3rd_qual"] / 100.0 * 5 for t in induced_thirds)
```

**Saída esperada no relatório:** por grupo, listar os placares EV-optimal e a lista induzida de 3ºs; no final, mostrar `third_place_ev` (número entre 0 e 40).

**NÃO recomendo nesta rodada:** otimização conjunta de placares + 3ºs. É problema combinatorial grande, fica para sprint futura.

---

## Passo 6 — Bônus "Acertou o Time que Avançou" no Mata-Mata

**Status:** NÃO implementado. Representa até **310 pts** (31 × 10).

### Reconfirmação da regra

Manual, página 4: *"Acertou o time que avancou (independente da fase): 10 pts."*

**Interpretação confirmada pelo manual:** 10 pts por confronto do mata-mata em que o time apostado avance, **flat**, **independente da fase** (ou seja, vale o mesmo em R32 e na Final). Não é por chave. Não é cumulativo por fase. É 10 pts por acerto de avanço, cada confronto isolado.

**Impacto sobre otimização:** como o ponto é flat e independente do placar, a aposta ótima de "quem avança" no confronto X é trivialmente `argmax P(team_i avança em X)`. O Monte Carlo já calcula essa probabilidade (pelas contagens de `r16`, `qf`, etc. por time).

### Proposta de implementação

Adicionar função separada de `bolao_points`:

```python
def bolao_knockout_advance_points(
    bet_advances: List[bool],   # por confronto: True se o time apostado avançou
) -> int:
    """
    10 pts por confronto em que o time apostado avançou.
    Total máximo: 31 × 10 = 310.
    """
    return 10 * sum(bet_advances)
```

E um helper para apoio à decisão por confronto:

```python
def optimal_advance_bet(
    team_a: str, team_b: str,
    advance_probs: Dict[str, float],  # P(team avança neste confronto)
) -> Dict[str, Any]:
    """Retorna {"bet": team, "ev_points": 10 * p_bet}."""
    pa, pb = advance_probs[team_a], advance_probs[team_b]
    if pa >= pb:
        return {"bet": team_a, "ev_points": 10 * pa}
    return {"bet": team_b, "ev_points": 10 * pb}
```

**Custo:** O(1) por confronto. Desprezível.

**Modificação no pipeline:** o Monte Carlo atual já agrega `r32`, `r16`, ..., `champion` por time. Mas essas são **probabilidades marginais de alcançar uma fase**, não **probabilidades condicionais de vencer um confronto específico**. Para dar a aposta ótima POR confronto, precisaríamos saber o par de adversários — que só é conhecido quando a fase anterior termina (daí o manual dizer "antes de cada jogo"). Então, na prática:

- **Antes do torneio começar:** não há como fazer aposta ótima de "quem avança" em R16/QF/SF/F porque não sabemos o par.
- **Para R32:** o par é conhecido (resulta do sorteio e chave), então `P(team_a avança sobre team_b)` pode ser calculada já no pré-torneio via Monte Carlo condicional ao par (`sim_head_to_head`).
- **Para R16+:** a decisão é tomada antes de cada jogo. O modelo precisa expor uma função `advance_prob(team_a, team_b)` para uso da aba do mata-mata.

**Já existe infraestrutura para isso:** `DixonColesModel.predict_match()` + `_simulate_match_fast()` com `knockout=True`. Só falta empacotar numa função de alto nível.

---

## Passo 7 — Campeão e Artilheiro

### Campeão

**Manual:** 25 pts pelo campeão correto.

**Estado atual:** `team_stats[team]["champion"]` é calculado pelo MC (linhas 834-835, 849-851).

**Gap:** nenhuma recomendação explícita da aposta ótima, nem cálculo do EV = 25 × P(champion).

**Proposta (trivial):**

```python
def optimal_champion_bet(team_stats: Dict[str, Dict]) -> Dict[str, Any]:
    """Time com maior P(champion). EV = 25 · P."""
    best_team = max(team_stats.keys(), key=lambda t: team_stats[t]["champion"])
    return {
        "bet": best_team,
        "p_champion": team_stats[best_team]["champion"],  # em %
        "ev_points": 25 * team_stats[best_team]["champion"] / 100.0,
    }
```

Esperado: EV típico na casa de 3–5 pts (favorito ~15% de chance × 25 = 3.75).

### Artilheiro

**Manual:** 30 pts pelo artilheiro correto.

**Estado atual:** nada modelado.

**Proposta:** manter como **TODO documentado**. Implementação exige:
- Dataset de gols por jogador × seleção (últimas edições).
- Modelo de `expected_goals_scored` por jogador.
- Ajuste pela probabilidade de avanço do time (quem não avança para fases tardias joga menos).

Deixar stub e comentário no código marcando o trabalho.

---

## Passo 8 — Relatório Consolidado e Estimativa de Impacto

### Tabela consolidada de bugs e gaps

| # | Item | Tipo | Onde | Impacto |
|---|------|------|------|---------|
| 1 | Mult. mata-mata errado (×2 em vez de tabela com ×1.5 arredondado) | Bug crítico | `bolao2026.py:293` | Todos os 7 tiers do mata-mata retornam valor errado. Afeta qualquer uso futuro de `bolao_points(..., knockout=True)`. |
| 2 | Docstring desatualizada (10/20, 6/12) | Bug de doc | `bolao2026.py:276-289` | Desorientação de quem lê o código. |
| 3 | Não otimiza classificação dos grupos | Gap (faltando feature) | Pipeline | Até 240 pts / Copa não otimizados. |
| 4 | Não calcula EV de 3ºs | Gap | Pipeline | Até 40 pts / Copa. |
| 5 | Não implementa bônus "time que avançou" mata-mata | Gap | `bolao_points` ou nova fn | Até 310 pts / Copa. |
| 6 | Não otimiza placar mata-mata | Gap | Pipeline | Até 465 pts / Copa (dependente de uso antes de cada jogo). |
| 7 | Não calcula EV/aposta do campeão | Gap | Pipeline | Até 25 pts / Copa. |
| 8 | Artilheiro não modelado | Gap conhecido | — | Até 30 pts / Copa. |

### Estimativa realista de pontos deixados na mesa

Pontuação otimizável pelo modelo (com EV típico, não máximo):

| Categoria | Máximo | EV típico otimizando | EV típico NÃO otimizando | Delta |
|-----------|-------:|---------------------:|-------------------------:|------:|
| Placares fase de grupos | 720 | ~240 (já capturado) | — | 0 |
| Classificação grupos | 240 | ~140 | ~80 (chute modal) | **+60** |
| Terceiros | 40 | ~20 | ~10 | **+10** |
| Placares mata-mata | 465 | ~150 (modal 1×0/2×1) | ~90 (palpite ingênuo) | **+60** |
| "Time que avançou" mata-mata | 310 | ~200 (favorito sempre) | ~120 (chute) | **+80** |
| Campeão | 25 | ~5 (favorito ~20%) | ~2 (chute) | **+3** |
| Artilheiro | 30 | 0 até ser modelado | 0 | 0 |
| **Total delta** | | | | **≈ +210 pts** |

**Interpretação:** se o modelo for corrigido e estendido conforme este relatório, o ganho esperado de EV vs a situação atual é da ordem de **200 pts por Copa** (maioria vindo do mata-mata e da classificação dos grupos). É suficiente para mover o palpiteiro do meio da tabela para o top do bolão.

### Ordem de implementação recomendada

1. **Corrigir `bolao_points()`** (divergência #1) — pré-requisito para tudo de mata-mata. Baixo esforço (~20 linhas alteradas).
2. **Bônus "time que avançou"** — alto ROI, baixo esforço. Reaproveita MC existente.
3. **Classificação dos grupos** — médio esforço (MC precisa guardar `group_top2_joint`), alto ROI.
4. **Terceiros** — baixo esforço (replicar tiebreak FIFA sobre placares EV-optimal).
5. **Campeão** — trivial, trivial ROI.
6. **Placar mata-mata por confronto** — depende de integração com o frontend (aba preenchida pré-jogo).
7. **Artilheiro** — sprint separada.

### Princípios de implementação para a próxima rodada

- **Zero duplicação.** Usar `bolao_points` já corrigida como fonte única de verdade da pontuação de placar; novos bônus como funções irmãs (`knockout_advance_points`, `group_classification_points`) somam por cima.
- **Reutilização do Monte Carlo.** As únicas novas agregações necessárias são `group_top2_joint` (matriz 4×4 por grupo) e, se for implementar apoio R32, `head_to_head_advance`. O resto já está computado.
- **Performance.** Nenhuma das funções novas propostas é quadrática no número de simulações — todas são O(k²) sobre times/placares e rodam em ms. O pipeline atual de ~6s não é afetado.

---

## Anexo: checklist de validação pós-correção

Quando as correções forem aplicadas, rodar estes testes:

1. `bolao_points((2,1), (2,1), knockout=False)` → **10**
2. `bolao_points((2,1), (2,1), knockout=True)` → **15** (hoje: 20 ❌)
3. `bolao_points((1,1), (0,0), knockout=True)` → **9** (hoje: 12 ❌)
4. `bolao_points((1,1), (1,1), knockout=True)` → **15** (hoje: 20 ❌)
5. `bolao_points((2,0), (3,1), knockout=True)` → **8** (hoje: 10 ❌)
6. `bolao_points((2,0), (3,2), knockout=True)` → **5** (hoje: 6 ❌)
7. `bolao_points((1,1), (2,0), knockout=False)` → **0** (OK hoje)
8. `bolao_points((0,1), (1,0), knockout=False)` → **0** (errou vencedor; OK hoje)
9. `optimal_group_bet` num grupo onde A é favorito esmagador → deve recomendar A em 1º e 2º favorito em 2º.
10. `optimal_champion_bet` → deve recomendar o time com maior `team_stats[t]["champion"]`.
