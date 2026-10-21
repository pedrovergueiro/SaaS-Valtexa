# Cérebro Agronômico Neuro-Simbólico com Raciocínio Causal e Agêntico

> Especificação do Pedro, recebida em 18/10/2026, transcrita como veio. Leia junto com
> `docs/RODADA4.md` (decisões, o que já existe, o que não pode).

## O salto tecnológico

A camada cognitiva deverá conectar os resultados numéricos dos modelos a um sistema de
explicação, consulta de conhecimento e planejamento.

O objetivo é permitir que o agrônomo compreenda não apenas o resultado da inferência, mas
também as evidências, as limitações e as alternativas de decisão.

## 8.1. Copiloto Fitossanitário Neuro-Simbólico

A arquitetura proposta combina:

- Um modelo de linguagem e visão.
- Um sistema de recuperação de informações por RAG.
- Um repositório de conhecimento agronômico.
- O histórico do talhão.
- Os resultados dos modelos visuais.
- Os dados meteorológicos.
- As regras determinísticas da plataforma.

### Fontes de conhecimento

O sistema poderá consultar fontes oficiais e técnicas, incluindo:

- Bulas e registros de produtos fitossanitários.
- Informações regulatórias do MAPA.
- Publicações técnicas da Embrapa.
- Escalas diagramáticas de severidade.
- Literatura científica sobre fitopatologia.
- Histórico de observações da propriedade.
- Dados do Gêmeo Digital e do FieldHistory.

As fontes devem ser versionadas e rastreáveis. Informações regulatórias precisam ser
verificadas em sua versão vigente antes de serem utilizadas em decisões operacionais.

## 8.2. Exemplo de Parecer Gerado pelo Agente

O exemplo abaixo é ilustrativo. Os valores, diagnósticos e condições mencionados não
representam uma medição real do sistema.

> Agrônomo, o sistema identificou sintomas foliares no Talhão 4, linha 22, planta 114. O
> classificador apresentou maior compatibilidade com Sigatoka, mantendo uma hipótese
> alternativa de Cordana. A imagem e os dados disponíveis ainda precisam ser avaliados quanto
> à qualidade e à suficiência das evidências. O histórico meteorológico poderá contribuir para
> a avaliação epidemiológica, desde que os dados de umidade, temperatura e molhamento foliar
> estejam disponíveis e tenham sido validados. O modelo de risco poderá estimar a evolução
> provável do foco, apresentando o horizonte de previsão, a incerteza e as limitações
> aplicáveis. Antes de qualquer recomendação de intervenção, o sistema deverá verificar o
> diagnóstico, a cultura, o registro vigente do produto, o alvo autorizado, a dose de bula, as
> restrições de aplicação, o intervalo de segurança e as condições ambientais. A recomendação
> final deverá ser revisada pelo profissional responsável e submetida às verificações
> determinísticas de segurança.

Esse formato permite gerar pareceres explicativos sem transformar probabilidades do modelo em
certezas agronômicas.

## 8.3. Planejamento e Otimização Estratégica

Além do diagnóstico, o agente poderá apoiar atividades de planejamento.

**Planejamento fitossanitário**

- Organizar os casos que precisam de revisão.
- Comparar o histórico de sintomas.
- Identificar regiões prioritárias para inspeção.
- Apresentar alternativas de manejo.
- Apoiar a avaliação de estratégias de rotação de ingredientes ativos, respeitando os
  registros e as recomendações aplicáveis.

**Planejamento robótico**

- Sugerir rotas com menor custo operacional.
- Considerar inclinação do terreno e obstáculos.
- Avaliar o estado da bateria.
- Distribuir tarefas entre dispositivos.
- Priorizar regiões com maior risco ou incerteza.

**Planejamento de insumos**

- Estimar a demanda com base no histórico de utilização.
- Projetar cenários de consumo.
- Identificar possíveis necessidades de reposição.
- Apresentar intervalos de confiança ou cenários alternativos.

Essas funcionalidades devem ser implementadas como mecanismos de apoio à decisão, com registro
das premissas e possibilidade de revisão humana.

## 8.4. O Princípio de Ouro da ValTexa

A evolução da inteligência artificial não deve comprometer a segurança operacional. A
arquitetura deve preservar a seguinte regra:

> **O agente raciocina, explica e propõe. O agrônomo responsável valida e autoriza. O Safety
> Engine determinístico verifica as condições de segurança e libera a execução somente quando
> todos os requisitos forem atendidos.**

Esse princípio deve permanecer válido mesmo quando os modelos se tornarem mais sofisticados ou
autônomos.
