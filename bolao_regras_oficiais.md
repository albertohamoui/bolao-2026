# Regras Oficiais do Bolão do Zap — Copa do Mundo 2026

**Fonte:** `manual_bolao_do_zap.pdf` (Manual do Participante, bolaodozap.com)
**Data da extração:** 2026-04-22
**Status:** Gabarito canônico. Onde o código divergir desta tabela, o código está errado.

---

## 1. Pontuação de Placares — Fase de Grupos

*Fonte: Manual, página 4 — seção "Regras de Pontuação → Placares — Fase de Grupos".*

| Tier | Resultado | Pontos |
|------|-----------|-------:|
| G1 | Placar exato (com vitória) | **10** |
| G2 | Diferença de gols certa (ex: ganhou por 1, apostou ganhar por 1) | **6** |
| G3 | Gols do vencedor certos (ex: real 2×1, apostou 2×0) | **5** |
| G4 | Gols do perdedor certos (ex: real 2×1, apostou 3×1) | **4** |
| G5 | Só o vencedor certo (sem acertar nenhum placar) | **3** |
| G6 | Empate exato (placar certo) | **10** |
| G7 | Empate certo, placar errado (ex: real 0×0, apostou 1×1) | **6** |
| G8 | Apostou empate mas não foi empate, ou errou o vencedor | **0** |

**Tiers mutuamente exclusivos:** o tier mais alto que aplica é o que conta.

---

## 2. Pontuação de Placares — Mata-Mata

*Fonte: Manual, página 4 — seção "Mata-Mata — Placares e Classificacao".*

O manual descreve a pontuação como `valor_grupos × 1.5`, mas **tabula os valores finais em inteiros já arredondados**. Os valores canônicos são os da coluna direita:

| Tier | Resultado | Fórmula manual | Pontos canônicos |
|------|-----------|----------------|-----------------:|
| K1 | Placar exato (após 90min ou 120min) | 10 × 1.5 | **15** |
| K2 | Diferença de gols certa | 6 × 1.5 | **9** |
| K3 | Gols do vencedor certos | 5 × 1.5 = 7.5 | **8** (arredondado) |
| K4 | Gols do perdedor certos | 4 × 1.5 | **6** |
| K5 | Só o vencedor certo | 3 × 1.5 = 4.5 | **5** (arredondado) |
| K6 | Empate exato (placar certo; decide nos pênaltis) | — | **15** |
| K7 | Empate certo, placar errado | — | **9** |
| K8 | Errou vencedor ou apostou empate em não-empate | — | **0** |

**IMPORTANTE:** o multiplicador ×1.5 **não é regular** porque o manual arredonda os tiers K3 (5 → 8, não 7.5) e K5 (3 → 5, não 4.5). Implementar o mata-mata como `grupos × 1.5` **produz resultados errados nesses dois tiers**. A tabela acima é a referência.

### Regra do empate no mata-mata

*Manual, página 4 — rodapé da tabela de mata-mata:*

> "no mata-mata, em caso de empate após prorrogação, você escolhe quem passa nos pênaltis. O placar vale como empate para fins de pontuação."

Isto significa:
- Se o palpite e o real forem empates (mesmo placar ou não), os tiers K6/K7 aplicam normalmente.
- A escolha do vencedor dos pênaltis é uma decisão **independente** do placar — afeta apenas o bônus "acertou o time que avançou" (ver §4), **não** os pontos de placar.
- Consequência prática: o palpite de classificação no mata-mata pode ser feito **independente** do palpite de placar. A aposta ótima de classificação é sempre `argmax P(team avança)`, independente do placar apostado.

---

## 3. Classificação dos Grupos (1º e 2º Colocados)

*Fonte: Manual, página 4 — seção "Classificacao dos Grupos (1o e 2o Colocados)".*

| Resultado | Pontos |
|-----------|-------:|
| Acertou o 1º colocado do grupo na posição exata | **10** |
| Acertou o 2º colocado do grupo na posição exata | **10** |
| Acertou que classificou, mas colocou na posição errada (1º↔2º) | **5** |

**Interações importantes:**
- São **dois palpites por grupo** (1º e 2º). O total máximo por grupo é **20 pts**.
- Os pontos dos dois palpites **não são independentes** — há cenários cruzados:
  - Aposto A em 1º, B em 2º. Real: A foi 2º, B foi 1º → ganho **5 + 5 = 10** pts (um ponto por palpite errado de posição, mas time classificado).
  - Aposto A em 1º, B em 2º. Real: A foi 1º, C foi 2º → ganho **10 + 0 = 10** pts.
  - Aposto A em 1º, B em 2º. Real: A foi 1º, B foi 2º → ganho **10 + 10 = 20** pts.
- A otimização precisa da **distribuição conjunta** P(1º=X, 2º=Y) por grupo, não só das marginais.

**Observação sobre como se faz o palpite:** o manual (página 3) deixa claro que o usuário **não preenche explicitamente** a classificação — ela é **derivada automaticamente** pelo sistema a partir dos palpites de placar, seguindo os critérios FIFA (pontos → saldo → gols marcados → confronto direto). Portanto, otimizar a classificação implica otimizar os placares do grupo para induzir a tabela desejada. Essa otimização conjunta é problema duro; a aproximação razoável é calcular a classificação induzida pelos placares EV-optimal já escolhidos e reportar o EV resultante.

---

## 4. Bônus de Terceiros Colocados que Avançam

*Fonte: Manual, página 4 — seção "Terceiros Colocados que Avancam".*

> "Para cada 3º colocado que você acertou entre os 8 que avançaram para o mata-mata: **5 pts**."

- Máximo: 8 × 5 = **40 pts**.
- Também é derivado automaticamente dos placares (manual, página 3, aba "3os Colocados"): o sistema pega os 8 melhores 3ºs conforme a tabela induzida pelos seus palpites, usando critérios FIFA (pts → saldo → gols marcados).
- O usuário não preenche nada; o placar apostado nos grupos determina os 3ºs induzidos.

---

## 5. Bônus do Mata-Mata — "Acertou o Time que Avançou"

*Fonte: Manual, página 4 — última linha da tabela de mata-mata.*

> "Acertou o time que avançou (**independente da fase**): **10 pts**."

**Semântica crítica:**
- Aplica-se a **cada confronto do mata-mata** (R32, R16, Quartas, Semifinal, Final).
- Vale **10 pts por confronto**, independente do tier do placar — é **componente adicional** ao placar, não substituto.
- **Independente da fase** significa que é o mesmo valor em R32 e na Final; NÃO significa "acumula por fase" — cada avanço correto vale 10 pts uma única vez.
- Total máximo: 31 jogos do mata-mata (16 R32 + 8 R16 + 4 QF + 2 SF + 1 F) × 10 = **310 pts**.

**Otimização:** como a pontuação é flat por confronto e independente do placar, a escolha ótima de "quem avança" é simplesmente `argmax P(team avança neste confronto)`, calculado a partir do Monte Carlo.

---

## 6. Bônus Especiais — Campeão e Artilheiro

*Fonte: Manual, página 5 — seção "Bônus Especiais".*

| Bônus | Condição | Pontos |
|-------|----------|-------:|
| Campeão | Acertou o campeão da Copa | **25** |
| Artilheiro | Acertou o artilheiro da Copa | **30** |

- Palpite único por participante (manual, página 2 — aba "Campeão" e "Artilheiro", prazo 11/6 às 11h).
- Aposta ótima de campeão: time com maior `P(champion)` do Monte Carlo (EV = 25 × P).
- Aposta ótima de artilheiro: requer modelagem por jogador (não coberto pelo modelo atual; TODO).

---

## 7. Pontuação Máxima Teórica

Somando todos os componentes:

| Categoria | Máximo |
|-----------|-------:|
| Placares fase de grupos (72 × 10) | 720 |
| Classificação grupos (12 × 20) | 240 |
| Terceiros (8 × 5) | 40 |
| Placares mata-mata (31 × 15) | 465 |
| "Time que avançou" mata-mata (31 × 10) | 310 |
| Campeão | 25 |
| Artilheiro | 30 |
| **Total** | **1830** |

> Nota: o manual na página 5 lista seis categorias de ranking (Pl, Cl, 3os, MM, Camp, Art). A categoria **MM** inclui "placares + classificação" do mata-mata, ou seja, é a soma dos componentes 4 e 5 desta seção.

---

## 8. Datas e Prazos (não afetam pontuação, mas são parte do manual)

*Fonte: Manual, página 1.*

- Prazo final para palpites: **11 de junho de 2026 — 11h**
- Abertura da Copa: **11 de junho de 2026**
- Encerramento da fase de grupos: **27 de junho de 2026**
- Início do mata-mata: **28 de junho de 2026**
- Final: **19 de julho de 2026**

Observação: mata-mata é preenchido **antes de cada jogo** (página 2 e 5), não em lote no prazo inicial.
