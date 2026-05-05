# Auditoria v2 — Manual Novo vs Manual Antigo e Impacto no Codigo

**Arquivos comparados:**
- `bolao_regras_oficiais.md` — gabarito extraido do manual ANTIGO (2026-04-22)
- `bolao_regras_oficiais_v2.md` — gabarito extraido do manual NOVO (2026-04-23)
- `manual_bolao_do_zap.pdf` — manual novo (versao atualizada)
- `bolao2026.py` — codigo com Passo 1 implementado
- `test_bolao_points.py` — testes unitarios
- `auditoria_bolao.md` — relatorio da auditoria anterior

**Data da auditoria:** 2026-04-23

---

## 1. Resumo Executivo

**Mudancas encontradas: 4**
- **CRITICAS (exigem mudanca em codigo ja implementado): 0**
- **ALTAS (mudam planejamento dos passos 2-6 ou prazos): 2**
- **BAIXAS (cosmeticas/documentacao/operacionais): 2**

**Conclusao principal:** a pontuacao NAO mudou em NENHUM componente. Todas as tabelas, bonus e valores sao identicos entre os dois manuais. O codigo implementado (`bolao_points`, `_POINTS_GROUP`, `_POINTS_KNOCKOUT`) esta correto e nao precisa de nenhum ajuste. Os testes em `test_bolao_points.py` continuam validos.

A unica mudanca com impacto no planejamento e a forma de preenchimento do mata-mata: bracket completo de uma vez (nao "antes de cada jogo"), o que afeta a estrategia de otimizacao dos Passos 2-6.

---

## 2. Diff Regra a Regra

### 2.1 Placares — Fase de Grupos (7 tiers)

| Tier | Antigo (bolao_regras_oficiais.md §1) | Novo (PDF pag. 4) | Status |
|------|--------------------------------------|---------------------|--------|
| G1 Placar exato | 10 pts | 10 pts | IDENTICO |
| G2 Diferenca de gols | 6 pts | 6 pts | IDENTICO |
| G3 Gols do vencedor | 5 pts | 5 pts | IDENTICO |
| G4 Gols do perdedor | 4 pts | 4 pts | IDENTICO |
| G5 So o vencedor | 3 pts | 3 pts | IDENTICO |
| G6 Empate exato | 10 pts | 10 pts | IDENTICO |
| G7 Empate placar errado | 6 pts | 6 pts | IDENTICO |
| G8 Errou tudo | 0 pts | 0 pts | IDENTICO |

### 2.2 Placares — Mata-Mata (7 tiers)

| Tier | Antigo (bolao_regras_oficiais.md §2) | Novo (PDF pag. 4) | Status |
|------|--------------------------------------|---------------------|--------|
| K1 Placar exato | 15 pts | 15 pts | IDENTICO |
| K2 Diferenca de gols | 9 pts | 9 pts | IDENTICO |
| K3 Gols do vencedor | 8 pts | 8 pts | IDENTICO |
| K4 Gols do perdedor | 6 pts | 6 pts | IDENTICO |
| K5 So o vencedor | 5 pts | 5 pts | IDENTICO |
| K6 Empate exato | 15 pts | 15 pts | IDENTICO |
| K7 Empate placar errado | 9 pts | 9 pts | IDENTICO |
| K8 Errou tudo | 0 pts | 0 pts | IDENTICO |

**Nota cosmetica:** o manual antigo mencionava explicitamente a formula "x1.5" com arredondamento. O manual novo lista apenas os valores finais (15, 9, 8, 6, 5, 15, 9). Os numeros sao identicos — a formula sumiu do texto mas os valores nao mudaram.

### 2.3 Bonus Classificacao dos Grupos (1o, 2o, troca de posicao)

| Regra | Antigo (§3) | Novo (PDF pag. 4) | Status |
|-------|-------------|---------------------|--------|
| 1o na posicao exata | 10 pts | 10 pts | IDENTICO |
| 2o na posicao exata | 10 pts | 10 pts | IDENTICO |
| Classificou mas posicao trocada | 5 pts | 5 pts | IDENTICO |

### 2.4 Bonus Terceiros Colocados Qualificados

| Regra | Antigo (§4) | Novo (PDF pag. 4) | Status |
|-------|-------------|---------------------|--------|
| Por cada 3o acertado entre os 8 | 5 pts | 5 pts | IDENTICO |

### 2.5 Bonus "Time que Avancou" no Mata-Mata

| Regra | Antigo (§5) | Novo (PDF pag. 4) | Status |
|-------|-------------|---------------------|--------|
| Acertou o time que avancou (qualquer fase) | 10 pts | 10 pts | IDENTICO |

### 2.6 Bonus Campeao

| Regra | Antigo (§6) | Novo (PDF pag. 5) | Status |
|-------|-------------|---------------------|--------|
| Acertou o campeao | 25 pts | 25 pts | IDENTICO |

### 2.7 Bonus Artilheiro

| Regra | Antigo (§6) | Novo (PDF pag. 5) | Status |
|-------|-------------|---------------------|--------|
| Acertou o artilheiro | 30 pts | 30 pts | IDENTICO |

**NOVO detalhe (PDF pag. 3):** "o nome do artilheiro deve ser escrito exatamente como aparece na camisa do jogador na Copa do Mundo 2026. Esse sera o criterio usado no gabarito. Uma diferenca de letra ou acento fara com que o palpite nao seja computado."

- **Status: NOVO** (detalhe operacional, nao afeta pontuacao nem modelo)
- Impacto: zero no codigo. Relevante apenas para o palpite manual do usuario.

### 2.8 Regra de Empate no Mata-Mata (penaltis)

| Aspecto | Antigo (§2, rodape) | Novo (PDF pag. 3) | Status |
|---------|---------------------|---------------------|--------|
| Mecanica | "voce escolhe quem passa nos penaltis" | "o sistema abre um campo para voce escolher quem passa nos penaltis" | IDENTICO (substancia) |
| Placar como empate | "O placar vale como empate para fins de pontuacao" | "O placar continua valendo como empate para fins de pontuacao" | IDENTICO |

**A assumption critica da auditoria anterior permanece valida:** a escolha de quem passa nos penaltis e independente do placar. O design fatorado (regime vitoria vs regime empate + bonus "avancou") continua correto.

### 2.9 Prazo de Submissao

| Aspecto | Antigo (§8) | Novo (PDF pag. 1) | Status |
|---------|-------------|---------------------|--------|
| Prazo fase de grupos + campeao + artilheiro | 11/6/2026 as 11h | **7/6/2026 as 23h59** | **MUDOU** |
| Descricao do prazo de mata-mata | "preenchido antes de cada jogo" | **"bracket completo de uma vez, apos 27/6"** | **MUDOU** |

### 2.10 Formato de Submissao do Mata-Mata

| Aspecto | Antigo (§8, §5) | Novo (PDF pag. 3) | Status |
|---------|-----------------|---------------------|--------|
| Quando preenche | "antes de cada jogo" (pag 2 e 5 do manual antigo) | **"bracket completo de uma vez"** apos 27/6 | **MUDOU** |
| Como funciona | Implicito: preenche confronto por confronto a medida que a fase avanca | "O vencedor de cada jogo avanca automaticamente para o proximo confronto no seu bracket" | **MUDOU** |

> **SINALIZACAO:** esta mudanca CONTRADIZ uma assumption usada na auditoria anterior (`auditoria_bolao.md`, Passo 6):
>
> A auditoria anterior (§6) dizia:
> - "Para R16+: a decisao e tomada antes de cada jogo. O modelo precisa expor uma funcao `advance_prob(team_a, team_b)` para uso da aba do mata-mata."
> - "Antes do torneio comecar: nao ha como fazer aposta otima de 'quem avanca' em R16/QF/SF/F porque nao sabemos o par."
>
> **No manual novo, o bracket e preenchido INTEIRO de uma vez apos a fase de grupos.** O participante:
> 1. Ve os confrontos reais de R32 (determinados pela classificacao real dos grupos)
> 2. Preenche placar + vencedor de TODOS os 31 jogos do mata-mata de uma vez
> 3. O vencedor de cada confronto avanca automaticamente para o proximo no bracket
>
> **Isto muda fundamentalmente a otimizacao:** agora o participante CONHECE os pares de R32 (sao os reais), mas os pares de R16+ dependem de QUEM ELE APOSTOU que avancaria nas fases anteriores. O bracket e auto-consistente: se voce aposta que o Brasil vence as oitavas, ele aparece como adversario de quem voce apostou na outra chave nas quartas.
>
> A otimizacao nao e mais "por confronto isolado" — e uma otimizacao de ARVORE DE BRACKET COMPLETA.

### 2.11 Outras secoes presentes apenas no manual novo

| Secao | Status | Descricao |
|-------|--------|-----------|
| Ranking (categorias Pl/Cl/3os/MM/Camp/Art) | NOVO (PDF pag. 5) | Descricao das 6 categorias do ranking. Manual antigo mencionava brevemente; novo detalha. Nao afeta pontuacao. |
| Aba Resultados | NOVO (PDF pag. 5) | "Apos 7/6, a aba Resultados fica disponivel" — informativo, nao afeta modelo. |
| Instrucoes de login (Supabase) | NOVO (PDF pag. 2) | Operacional. Nao afeta modelo. |
| "Salvar grupo a grupo" ou "Salvar Tudo" | NOVO (PDF pag. 3) | UX do site. Nao afeta modelo. |

---

## 3. Impacto no Codigo Atual

### 3.1 Impacto em `bolao_points()` / `_POINTS_GROUP` / `_POINTS_KNOCKOUT`

**Nenhum.** Todos os valores de pontuacao sao identicos. As tabelas em `bolao2026.py:277-296` estao corretas conforme o manual novo. Os testes em `test_bolao_points.py` (24 testes) continuam todos validos.

### 3.2 Impacto em `ev_optimal_score()`

**Nenhum.** A funcao calcula EV sobre a distribuicao de placares usando `bolao_points`, que nao mudou.

### 3.3 Impacto em `knockout_advance_points()`

**Nenhum.** 10 pts por acerto de avanco, identico ao manual novo.

### 3.4 Impacto em `optimal_knockout_bet()`

**Funcao em si: nenhum.** Os valores que ela usa (via `bolao_points(..., knockout=True)`) nao mudaram.

**Porem, a FORMA DE USO muda:** a funcao foi projetada para otimizar um confronto isolado. Com o bracket completo preenchido de uma vez, a otimizacao deveria considerar a arvore completa (quem voce aposta que vence em R32 determina quem aparece em R16, etc.). A funcao continua util como building block, mas a camada acima (que decide o bracket otimo) precisa ser redesenhada.

### 3.5 Impacto em `optimal_group_bet()`, `optimal_champion_bet()`, funcoes de 3os

**Nenhum.** Pontuacao identica.

### 3.6 Impacto em assumptions implementadas ou acordadas

| Assumption | Status |
|------------|--------|
| "placar vale como empate para fins de pontuacao" (auditoria §2) | **CONFIRMADA** pelo manual novo |
| "escolha de quem passa nos penaltis e independente do placar" (auditoria §2) | **CONFIRMADA** pelo manual novo |
| "formulacao fatorada: regime vitoria vs regime empate + bonus avancou" (auditoria §6) | **CONFIRMADA** — a mecanica nao mudou |
| "otimizacao de mata-mata e feita antes de cada jogo" (auditoria §6) | **INVALIDADA** — bracket e completo de uma vez |
| "para R16+, nao sabemos o par" (auditoria §6) | **PARCIALMENTE INVALIDADA** — o par depende do proprio bracket do participante |

### 3.7 Regras NOVAS que precisariam virar codigo

| Regra nova | Precisa de codigo? |
|------------|-------------------|
| Nome do artilheiro = camisa | Nao — validacao e do site, nao do modelo |
| Bracket completo de uma vez | Nao e "regra de pontuacao" nova, mas muda a FORMA de otimizacao (ver §4) |

---

## 4. Impacto nos Passos Pendentes do Plano Anterior

### Passo 2 (auditoria_bolao.md) — Bonus "time que avancou"

| Aspecto | Plano original | Manual novo | Veredicto |
|---------|---------------|-------------|-----------|
| Valor | 10 pts flat por confronto | 10 pts (qualquer fase) | **VALIDO** |
| Independente da fase? | Sim | Sim | **VALIDO** |
| Estrutura (chave certa/errada)? | Nao, flat | Nao, flat | **VALIDO** |

**Especificacao do Passo 2: CONTINUA VALIDA.** Nenhum ajuste necessario.

### Passo 3 (auditoria_bolao.md) — Classificacao dos grupos

| Aspecto | Plano original | Manual novo | Veredicto |
|---------|---------------|-------------|-----------|
| Pontuacao 10/10/5 | Sim | Sim | **VALIDO** |
| Derivacao automatica dos placares | Sim | Sim | **VALIDO** |

**Especificacao do Passo 3: CONTINUA VALIDA.**

### Passo 4 (auditoria_bolao.md) — Terceiros colocados

| Aspecto | Plano original | Manual novo | Veredicto |
|---------|---------------|-------------|-----------|
| 5 pts por 3o acertado | Sim | Sim | **VALIDO** |
| 8 terceiros que avancam | Sim | Sim | **VALIDO** |

**Especificacao do Passo 4: CONTINUA VALIDA.**

### Passo 5 (auditoria_bolao.md) — Campeao

| Aspecto | Plano original | Manual novo | Veredicto |
|---------|---------------|-------------|-----------|
| 25 pts | Sim | Sim | **VALIDO** |

**Especificacao do Passo 5: CONTINUA VALIDA.**

### Passo 6 (auditoria_bolao.md) — Placar mata-mata por confronto

| Aspecto | Plano original | Manual novo | Veredicto |
|---------|---------------|-------------|-----------|
| Pontuacao dos tiers | Identica | Identica | **VALIDO** |
| Forma de preenchimento | "antes de cada jogo" | **"bracket completo de uma vez"** | **PRECISA AJUSTE** |
| Otimizacao por confronto isolado | Sim (advance_prob por par) | **Nao — precisa otimizar arvore completa** | **PRECISA AJUSTE** |

**Especificacao do Passo 6: PRECISA AJUSTE.** Ver detalhamento abaixo.

### Bonus novos?

| Bonus hipotetico | Presente no manual novo? |
|------------------|--------------------------|
| Vice-campeao | Nao |
| 3o colocado do torneio | Nao |
| Melhor defesa | Nao |
| Qualquer outro bonus | Nao |

**Nenhum bonus novo.** A lista de componentes a otimizar nao mudou.

---

## 5. Detalhamento da Mudanca ALTA: Bracket Completo

### O que mudou

**Antes (manual antigo):** o participante preenchia o mata-mata "antes de cada jogo", ou seja, sequencialmente a medida que as fases avancavam. Sabia os pares reais de cada fase antes de palpitar.

**Agora (manual novo):** o participante preenche o bracket INTEIRO de uma vez apos 27/6. Os confrontos de R32 sao conhecidos (sao os reais). Para R16+, os confrontos dependem de quem o participante apostou que venceria nas fases anteriores. O bracket e uma arvore auto-consistente.

### Impacto na otimizacao

A funcao `optimal_knockout_bet()` em `bolao2026.py:387-498` esta desenhada para otimizar UM confronto isolado. Ela recebe `score_matrix` e `p_advance_home` para um par especifico e retorna o palpite otimo.

Com bracket completo, a otimizacao ideal seria:

1. **R32 (16 jogos):** pares conhecidos (reais). Pode usar `optimal_knockout_bet` diretamente. **Sem mudanca.**

2. **R16 (8 jogos):** pares dependem de quem o participante apostou em R32. O participante sabe quem ele proprio apostou, entao os pares de R16 sao determinados pelo bracket. Pode usar `optimal_knockout_bet` com os pares induzidos. **Mudanca: precisa cascatear o bracket.**

3. **QF, SF, Final:** idem, cascateando o bracket.

**Abordagem pragmatica:** como o bonus de "time que avancou" (10 pts) e aditivo e flat, e o placar de cada jogo e avaliado independentemente, a otimizacao POR CONFRONTO continua sendo uma boa aproximacao. A diferenca e que os PARES dos confrontos de R16+ nao sao os reais — sao os do bracket do participante.

**Abordagem rigorosa (opcional, complexidade alta):** otimizar o bracket como arvore. Para cada cenario do MC, simular o bracket real E o bracket apostado, calculando os pontos totais. Maximizar sobre todas as arvores possiveis. Isso e exponencial no numero de times (2^31 brackets possiveis) — inviavel por forca bruta. Heuristicas necessarias.

**Recomendacao:** manter a otimizacao por confronto como v1. O bracket do participante sera construido top-down (comecar apostando o campeao, depois preencher o bracket de forma consistente com essa aposta). A funcao `optimal_knockout_bet` serve como building block para cada confronto induzido.

### Impacto na funcao `optimal_knockout_bet`

A funcao em si NAO muda. O que muda e como ela e CHAMADA:
- Antes: chamada com pares reais, um por vez, antes de cada jogo.
- Agora: chamada com pares induzidos pelo bracket, todos de uma vez, cascateando de R32 para a Final.

**Proposta de nova funcao wrapper:**

```python
def optimal_full_bracket(
    r32_matchups: List[Tuple[str, str]],   # 16 pares reais de R32
    model: DixonColesModel,
    cal: Calibration,
) -> Dict[str, Any]:
    """
    Constroi bracket EV-optimal completo, cascateando fase a fase.
    
    Para cada confronto, usa optimal_knockout_bet com score_matrix do par
    e p_advance do Monte Carlo. O vencedor apostado avanca para o proximo
    confronto no bracket.
    """
    # R32: 16 confrontos com pares reais
    # R16: 8 confrontos com vencedores apostados de R32
    # QF: 4 confrontos com vencedores apostados de R16
    # SF: 2 confrontos com vencedores apostados de QF
    # Final: 1 confronto com vencedores apostados de SF
    pass
```

Essa funcao so sera util apos 27/6, quando os pares de R32 forem conhecidos.

---

## 6. Tabela Consolidada de Mudancas

| # | Mudanca | Severidade | Afeta | Acao |
|---|---------|-----------|-------|------|
| 1 | Prazo mudou de 11/6 11h para 7/6 23h59 | **ALTA** (planejamento) | Planejamento + Documentacao | Deadline 4 dias antes — ver PRAZOS.md |
| 2 | Formula x1.5 removida do texto (valores identicos) | BAIXA | Documentacao | Nenhuma — `bolao_regras_oficiais_v2.md` ja reflete |
| 3 | Nome do artilheiro = camisa (novo detalhe) | BAIXA | Operacional | Nenhuma acao de codigo |
| 4 | Bracket completo de uma vez (nao "antes de cada jogo") | **ALTA** | Planejamento (Passo 6) | Redesenhar camada de otimizacao de bracket; `optimal_knockout_bet` continua util como building block |

### Revisao do "EV recuperavel"

A estimativa da auditoria anterior (auditoria_bolao.md §8):
- Delta EV total: ~210 pts
- Breakdown por componente: classificacao (+60), 3os (+10), placar mata-mata (+60), "time que avancou" (+80), campeao (+3)

**Com o manual novo, NENHUM peso mudou.** A estimativa de EV recuperavel permanece identica: **~210 pts de delta**.

A mudanca de bracket afeta apenas a FORMA de otimizacao (arvore vs confronto isolado), nao o valor esperado dos componentes.

---

## 7. Plano de Acao Recomendado

**Prioridade 1 — Nao fazer nada no codigo de pontuacao.**
O Passo 1 da auditoria anterior (correcao de `bolao_points`) ja foi implementado e esta CORRETO. Os testes passam. Nenhuma mudanca necessaria.

**Prioridade 2 — Implementar Passos 2-5 conforme planejado.**
Todas as especificacoes dos Passos 2-5 da auditoria anterior continuam validas:
- Passo 2: bonus "time que avancou" (10 pts flat) — ja implementado como `knockout_advance_points`
- Passo 3: classificacao dos grupos (10/10/5) — ja implementado como `optimal_group_bet`
- Passo 4: terceiros colocados (5 pts) — ja implementado como `induced_third_places` + `third_places_ev`
- Passo 5: campeao (25 pts) — ja implementado como `optimal_champion_bet`

**Nota:** revisando o codigo em `bolao2026.py`, vejo que os Passos 2-5 JA FORAM IMPLEMENTADOS (funcoes `knockout_advance_points`, `optimal_group_bet`, `optimal_champion_bet`, `induced_third_places`, `third_places_ev`, `optimal_knockout_bet`). O pipeline `run_full_pipeline` ja chama `optimal_group_bet`, `optimal_champion_bet`, e `induced_third_places`/`third_places_ev`.

**Prioridade 3 — Ajustar Passo 6 (bracket completo).**
Quando os pares de R32 forem conhecidos (apos 27/6):
- Implementar `optimal_full_bracket` que cascateia `optimal_knockout_bet` fase a fase
- Usar os pares reais de R32 como input
- Construir bracket auto-consistente (vencedor apostado avanca)
- Isso nao e urgente — so sera util apos 27/6

**Prioridade 4 — Atualizar documentacao.**
- Prazo: 7/6 23h59 (nao 11/6 11h)
- Bracket: completo de uma vez (nao "antes de cada jogo")
- Artilheiro: nome = camisa

---

## 8. Conclusao

O manual novo e essencialmente identico ao antigo em termos de pontuacao. As 4 mudancas encontradas sao 3 cosmeticas/operacionais e 1 de forma de preenchimento (bracket completo). Nenhuma mudanca afeta codigo ja implementado. A unica acao de medio prazo e preparar uma funcao de otimizacao de bracket completo para uso apos 27/6.
