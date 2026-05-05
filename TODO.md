# TODO — Bolão 2026

Lista de trabalhos pendentes que excedem o escopo das sprints atuais.

---

## Artilheiro da Copa (bônus de 30 pts)

**Status:** não modelado. `optimal_champion_bet` já existe para o bônus do campeão (25 pts), mas artilheiro não tem análogo.

**Fonte da regra:** `manual_bolao_do_zap.pdf` pág. 5 — "Artilheiro: Acertou o artilheiro da Copa → 30 pts".

### O que seria necessário

1. **Dataset de gols por jogador × seleção**
   - Jogos oficiais pós-2022 (eliminatórias + amistosos + Nations League).
   - Para competições de clubes de 2024–2026 (ponderado — gols na Champions pesam diferente de gol em amistoso).
   - Fontes: Transfermarkt, SofaScore, FBref (scraping).

2. **Modelo de `expected_goals_per_match` por jogador**
   - Baseline: média de gols/jogo nas últimas N partidas ponderada por nível do adversário.
   - Refinamento: mix com xG (se disponível) para filtrar jogadores "sortudos" com finalizações acima do esperado.

3. **Modelo de minutos esperados na Copa**
   - Probabilidade do jogador começar cada jogo × probabilidade da seleção avançar cada fase.
   - P(seleção avançar) já vem do Monte Carlo atual (`team_stats[t]["r32"..."champion"]`).
   - P(jogador ser titular | seleção joga) vem do perfil recente.

4. **Agregação: `P(jogador é artilheiro)`**
   - Simular N caminhos alternativos: `gols(jogador_i) = Poisson(lambda_i · minutos_esperados)`.
   - Artilheiro = argmax sobre todos os jogadores.
   - Contagem Monte Carlo de frequência → probabilidade por jogador.

5. **Aposta ótima**
   - `optimal_topscorer_bet` = argmax sobre `P(jogador é artilheiro)`.
   - EV = `30 × P(jogador)`.

### Estimativa de complexidade

- Coleta de dados: 1–2 dias (scraping + normalização de nomes).
- Modelagem: 2–3 dias (incluindo tuning com artilheiros históricos: Musiala 2024 Euro, Giroud/Mbappé 2022, etc).
- Integração no pipeline: 1 dia.
- Total: **~1 sprint**.

### Nota de calibração

Artilheiros recentes de Copa (2014, 2018, 2022):
- 2014: James Rodríguez (6 gols) — P prévia ~3–5% (não era entre os top 3 favoritos).
- 2018: Harry Kane (6 gols) — P prévia ~8% (era favorito claro).
- 2022: Mbappé (8 gols) — P prévia ~10–12% (top favorito).

Histórico: artilheiro médio faz 5–8 gols, vem de time que chega às semifinais. EV típico de aposta ótima deve ficar em torno de 30 · 0.10 = **3 pts**.

### Contra-argumento "vale a pena?"

Vale:
- Qualquer aposta é melhor que 0 (hoje deixamos 0 pts garantidos na mesa).
- A apostar *algum* jogador do favorito (Spain/Brazil/France) já capta ~3% de EV sem modelagem sofisticada.

Mas:
- Ganho marginal sobre "aposta um craque do favorito" (baseline humano) é pequeno: talvez +1 a +2 pts esperados.
- O custo de coleta é alto e o dataset envelhece rápido (lesões, mudanças de forma próximas do torneio).

**Recomendação:** deixar dormente até 2–3 semanas antes do torneio, quando jogadores lesionados já estão definidos e squads fechados. Fazer versão simplificada (só usar gols em eliminatórias + xG em clube da temporada) em vez de modelo completo.
