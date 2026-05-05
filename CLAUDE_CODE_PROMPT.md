# BOLAO 2026 - Briefing Completo para Claude Code

## CONTEXTO DO PROJETO

Estou construindo um modelo estatistico avancado para prever os resultados da Copa do Mundo FIFA 2026 para um bolao. O bolao exige placar exato de cada jogo + quem passa de fase. Preciso submeter todos os jogos da fase de grupos de uma vez antes da Copa comecar (11 de junho 2026), e depois submeter os jogos do mata-mata quando as chaves forem definidas.

O projeto esta no diretorio:
`/Users/albertohamoui/Library/CloudStorage/OneDrive-Personal/Bolão 2026/`

Arquivos existentes:
- `bolao2026.py` -- modelo principal (funcional, ~800 linhas)
- `results.csv` -- 49.215 jogos internacionais historicos (1872-2025)
- `bolao2026_results.json` -- output da ultima rodada

Para rodar: `python3 bolao2026.py`

## ARQUITETURA ATUAL DO MODELO

### Pipeline:
```
[49k jogos historicos] --> [Dixon-Coles calibrado com 538 jogos desde 2022]
                                        |
                              [Blend bayesiano 55% DC + 45% Elo]
                                        |
                              [Parametros ataque/defesa por selecao]
                                        |
                              [Distribuicao Poisson por jogo]
                                        |
                              [Monte Carlo 50k simulacoes do torneio]
                                        |
                              [Probabilidades + placares recomendados]
```

### O que cada componente faz:

1. **Dixon-Coles**: modelo que estima parametros de ataque e defesa para cada selecao a partir de resultados historicos. Melhoria sobre Poisson puro com correcao tau para placares baixos (0-0, 1-0, 0-1, 1-1) e time-decay (jogos recentes pesam mais).

2. **Blend bayesiano**: mistura os parametros do Dixon-Coles (55%) com priors derivados do Elo rating (45%). Isso corrige vieses do DC onde selecoes que jogam contra adversarios fracos ficam com ataque inflado (ex: Brasil goleando Bolivia nas eliminatorias).

3. **Monte Carlo**: simula 50.000 torneios completos (fase de grupos + mata-mata com prorrogacao e penaltis). Output: probabilidade de cada selecao em cada fase.

4. **Host advantage**: EUA, Mexico, Canada recebem +5% boost ofensivo.

5. **Ajuste expert**: dicionario EXPERT_ADJUSTMENTS onde eu aplico multiplicadores manuais por selecao.

### Dados embutidos no codigo:
- Elo ratings das 48 selecoes (eloratings.net, abril 2026)
- FIFA rankings (abril 2026)
- 12 grupos oficiais (sorteio dez/2025)
- Confederacoes de cada selecao

## ULTIMO OUTPUT DO MODELO

### Ranking de favoritos:
```
1. Spain       15.8%
2. Argentina   12.1%
3. France      11.2%
4. Brazil      10.0%
5. Portugal     6.8%
6. Colombia     5.5%
7. England      4.0%
8. Germany      3.5%
9. Uruguay      3.3%
10. Netherlands 3.1%
```

### Parametros calibrados (top 15):
```
Selecao                  Ataque   Defesa    Forca
Argentina                +0.484   -0.456    0.940
Spain                    +0.557   -0.371    0.929
France                   +0.523   -0.381    0.905
Portugal                 +0.417   -0.359    0.776
Colombia                 +0.420   -0.291    0.712
Brazil                   +0.500   -0.204    0.704
England                  +0.352   -0.218    0.570
Uruguay                  +0.190   -0.297    0.487
Croatia                  +0.221   -0.239    0.459
Germany                  +0.425   -0.026    0.452
Netherlands              +0.392   -0.044    0.436
Japan                    +0.280   -0.136    0.417
Austria                  +0.262   -0.113    0.374
Belgium                  +0.171   -0.084    0.255
Morocco                  +0.110   -0.135    0.245
```

## PROBLEMAS CONHECIDOS QUE PRECISAM SER CORRIGIDOS

### 1. Brasil ainda superestimado (10% titulo vs ~7% mercado)
O blend bayesiano ajudou mas o Brasil ainda tem ataque de +0.500 (2o maior) com defesa mediocre de -0.204. O mercado (casas de aposta) da ~7% pro Brasil. Nosso modelo da 10%.

### 2. Inglaterra subestimada (4.0% vs 12.4% mercado)
A Inglaterra tem o elenco mais caro do mundo (€1.3B) e o mercado da 12.4%. Nosso modelo da 4.0%. O Dixon-Coles nao captura a profundidade/qualidade do elenco ingles -- so ve os resultados, que sao mediocres pra qualidade dos jogadores.

### 3. Alemanha com defesa positiva (+0.026 = ruim)
A defesa da Alemanha aparece como levemente negativa, o que nao reflete a realidade de um time europeu forte.

### 4. Excesso de empates nos placares recomendados
Muitos jogos aparecem como 1x1 ou 0x0 mesmo quando um time e claramente favorito. Isso e artefato da Poisson com lambdas baixos -- o placar individual mais provavel tende a ser empate. Para o bolao, talvez a logica de "placar recomendado" devesse considerar: qual placar maximiza meu valor esperado de pontos?

### 5. Coluna "Final" duplica "Titulo" no output
A coluna "Final" esta mostrando o mesmo valor que "Titulo" -- deveria mostrar probabilidade de CHEGAR na final (que e maior que ganhar o titulo).

## O QUE PRECISA SER FEITO AGORA (Sprint 3)

### Adicionar variaveis extras ao modelo:

**1. Valor de mercado do elenco (Transfermarkt, marco 2026):**
Usar como proxy para profundidade e qualidade individual. Dados coletados:
- England: €1300M, France: €1280M, Spain: €920M, Portugal: €865M
- Brazil: €854M, Germany: €817M, Argentina: €600M, Netherlands: €712M
- Belgium: €549M, Colombia: ~€350M, Uruguay: ~€300M, Croatia: ~€350M
- Morocco: ~€250M, Japan: ~€200M, Mexico: ~€150M, Switzerland: ~€200M
- USA: ~€180M, South Korea: ~€150M, Ecuador: ~€120M, etc.
(estimar valores para selecoes menores proporcionalmente ao Elo)

A forma correta de incluir: normalizar os valores (0 a 1), e usar como terceiro componente no blend. Em vez de 55% DC + 45% Elo, fazer algo como 50% DC + 35% Elo + 15% Transfermarkt.

**2. Odds de mercado como benchmark (NAO como input):**
- Spain: 16.4%, France: ~14%, England: 12.4%, Argentina: 9.4%
- Brazil: ~7%, Germany: ~5%, Portugal: ~5%, Netherlands: ~4%
- Colombia: ~3%, Croatia: ~2.5%, Belgium: ~2%

Usar para validar se o modelo converge com o consensus do mercado. Nao usar diretamente como input (senao estamos so copiando as odds).

**3. xG por selecao nas eliminatorias (qualitativo):**
- Norway: xG 24.70 em 10 jogos UEFA (muito alto, Haaland effect)
- Australia: overperformou xG em +10 nas eliminatorias asiaticas
- Egypt: underperformou xG em -2.4 (dependencia do Salah)
- Brazil: xG alto mas contra adversarios fracos CONMEBOL

### Melhorias tecnicas:

**1. Logica de placar recomendado pro bolao:**
Em vez de sempre recomendar o placar mais provavel (que tende a ser empate), implementar logica que considere as regras de pontuacao do bolao. Se acertar placar exato da mais pontos que acertar so o vencedor, pode valer a pena arriscar um 1x0 em vez de jogar 1x1 seguro.

**2. Backtest contra Copas passadas (Sprint 2 pendente):**
Rodar o modelo contra Copa 2022 e medir: quantos resultados (V/E/D) acertou? Quantos placares exatos? Isso valida se o modelo funciona antes de confiar nele pro bolao real.

**3. Formato do torneio 2026:**
- 12 grupos de 4 times
- Top 2 + 8 melhores terceiros avancam (32 times)
- Round of 32 (novo!) > Round of 16 > Quartas > Semis > Final
- Total: 104 jogos, 39 dias

## PRINCIPIOS IMPORTANTES

1. **ZERO duplicidade de informacao.** Cada variavel entra uma vez pelo canal mais apropriado. O Elo ja captura forca geral. Transfermarkt adiciona profundidade de elenco. xG adiciona eficiencia ofensiva/defensiva real.

2. **Resultados devem convergir com o mercado.** Se as casas de aposta dao 16% pra Espanha e 12% pra Inglaterra, nosso modelo deve estar na mesma faixa. Divergencias grandes indicam erro no modelo, nao insight especial.

3. **Ajuste expert e pra coisas que dados nao capturam.** Lesoes de jogadores-chave, troca de tecnico recente, conflitos internos, motivacao. NAO para corrigir erros do modelo -- isso se corrige no modelo.

4. **Performance > estetica.** O modelo roda em 6 segundos com 50k simulacoes. Manter essa performance.

## STACK TECNICO

- Python 3.14 no Mac (VS Code)
- numpy, scipy, pandas
- Sem frameworks de ML ainda (XGBoost planejado pro Sprint 5 pos-grupos)
- Output em JSON + terminal

## COMO ME COMUNICAR

- Sou brasileiro, falo portugues e ingles fluentemente
- Prefiro explicacoes diretas e honestas, sem diplomatismo excessivo
- Tenho background em financas/dados (trabalho com credito estruturado)
- Entendo estatistica e probabilidade mas nao sou programador profissional
- Gosto de entender a teoria antes de implementar
- Nao uso emojis em documentos ou nomes de arquivo
