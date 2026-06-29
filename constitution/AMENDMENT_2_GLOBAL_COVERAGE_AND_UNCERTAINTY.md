# Alteração constitucional 2

Estado: `RATIFIED_FOR_RESEARCH_DEVELOPMENT`

Data de ratificação: 29 de Junho de 2026.

## Objecto

Autorizar uma construção mundial experimental do cabaz Armilar que cubra todas as economias do universo definido, sem alterar nem diluir a matriz estrita baseada em dados oficiais exactos ou em derivações oficiais determinísticas.

## Duas construções separadas

1. `ARM-WEIGHTS-CORE` aceita apenas células de classe A e B. É uma matriz observada e pode ser incompleta à escala mundial.
2. `ARM-WEIGHTS-GLOBAL` exige todas as economias e as doze categorias. Pode incluir células de classe C, D e E, sempre identificadas e acompanhadas por incerteza.

Nenhum output pode chamar mundial a uma matriz que apenas renormaliza o subconjunto observado.

## Classificação por célula

A classificação aplica-se a cada par economia-categoria:

- `A_OFFICIAL_EXACT`: dado oficial exacto no conceito, sector, transacção, ano, preços, unidade e categoria exigidos;
- `B_OFFICIAL_DETERMINISTIC`: derivação integralmente determinística de dados oficiais, sem alocação estatística;
- `C_OWN_ECONOMY_ESTIMATE`: estimativa baseada em dados oficiais ou observados da própria economia;
- `D_DONOR_IMPUTATION`: imputação baseada em economias comparáveis, com regra de selecção previamente definida;
- `E_REGIONAL_GLOBAL_FALLBACK`: fallback regional ou mundial usado quando não existe evidência suficiente da própria economia ou de doadores adequados.

Uma economia não recebe uma única classe global. Pode ter classes diferentes nas doze categorias.

## Requisitos das estimativas

Toda a célula C, D ou E deve publicar:

- valor central;
- limite inferior e limite superior;
- identificador do método;
- versão do modelo ou da regra;
- fontes utilizadas;
- economias doadoras, quando aplicável;
- resultados de validação disponíveis;
- motivo pelo qual não foi usada uma classe superior.

Os intervalos devem ser propagados para os pesos e, mais tarde, para o índice temporal.

## Limites constitucionais

Esta alteração não autoriza:

- apresentar estimativas como observações oficiais;
- apagar ou substituir a matriz strict;
- escolher doadores manualmente para obter um resultado desejado;
- omitir a classe de evidência;
- renormalizar silenciosamente economias em falta;
- utilizar a construção mundial experimental para política monetária antes de backtest, funcionamento em sombra e auditoria independente;
- alterar retrospectivamente o método de uma release já publicada;
- deixar uma célula sem fonte, método ou estado explícito.

## Substituição progressiva

Quando surgir uma célula de classe superior, esta substitui a célula inferior apenas numa nova release. A release anterior e a sua proveniência permanecem preservadas.

## Estado monetário

A aprovação desta alteração mantém `monetary_release_allowed=false`. A construção mundial é autorizada para investigação, validação e desenvolvimento do índice mensal.
