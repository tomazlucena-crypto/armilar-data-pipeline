# Alteração constitucional 1.1

Estado: `RATIFIED_FOR_RESEARCH_DEVELOPMENT`

Data de ratificação: 28 de Junho de 2026.

Base de ratificação: aprovação expressa do proprietário do projecto, “vamos avançar com a opção B”.

## Objecto

Autorizar uma via proxy separada para CP04, CP06, CP09, CP10 e CP12 quando a publicação pública do ICP não disponibiliza PPPs com âmbito estrito de HFCE das famílias.

## Regra ratificada

O numerador de cada célula continua a ser despesa doméstica oficial das famílias:

- sector S14;
- transacção P31DC;
- preços correntes;
- ano 2021;
- categoria COICOP reconciliada.

O PPP do heading de consumo efectivo seria usado apenas como deflator da despesa P31DC da mesma categoria e economia.

A regra não autoriza:

- introdução de despesa do Estado ou de NPISH no numerador;
- uso de AIC como peso nominal;
- repartição arbitrária de totais;
- substituição de dados domésticos ausentes;
- renormalização silenciosa;
- mistura da matriz proxy com a matriz strict sem identificação.

## Fórmula proxy

Para economia `i` e categoria `c`:

`real_proxy_i,c = nominal_P31DC_i,c / PPP_actual_consumption_i,c`

O peso proxy mundial seria:

`w_proxy_i,c = real_proxy_i,c / soma(real_proxy_j,k)`

A fórmula só pode ser aplicada quando existe cobertura mundial suficiente e todos os campos de proveniência estão confirmados.

## Risco económico

O PPP de consumo efectivo pode reflectir a combinação de preços, produtos e canais de financiamento do consumo das famílias, do Estado e de NPISH. Mesmo com um numerador exclusivamente P31DC, o deflator pode não representar exactamente o cabaz pago directamente pelas famílias.

## Gates de ratificação

Antes de qualquer uso monetário, exige-se:

1. comparação quantitativa strict versus proxy nas sete categorias em que ambos os PPPs existam ou possam ser aproximados oficialmente;
2. medição do enviesamento por economia, região e nível de rendimento;
3. teste de sensibilidade dos pesos mundiais;
4. confirmação de que o proxy melhora a comparabilidade face ao uso de câmbios de mercado;
5. publicação separada dos resultados strict e proxy;
6. aprovação expressa do proprietário do projecto.

## Consequência da ratificação

A Constituição permite uma matriz `PROXY_PPP_ACTUAL_CONSUMPTION` para as cinco categorias bloqueadas. A matriz strict manter-se-ia inalterada e continuaria a exigir PPPs household-only.
