# Inteligência de Enxame Heterogêneo e Consenso Federado

> Especificação do Pedro, recebida em 18/10/2026, transcrita como veio. **Leia junto com
> `docs/RODADA4.md`**: não existe mais base de comunicação na fazenda — cada Rover tem a sua
> Starlink. Onde o texto diz "a Base" coordena, verifica, funde ou distribui, esse papel é da
> **plataforma** (saas/), alcançada pela Starlink de cada dispositivo.

## O salto tecnológico

O objetivo é permitir que Rovers, drones e Base atuem como componentes coordenados de uma única
infraestrutura operacional.

A inteligência coletiva não depende apenas de conectar os dispositivos. Ela exige protocolos
consistentes, sincronização de informações e regras claras para distribuir tarefas.

## 7.1. Fusão Federada de Priores com dNATY

O mecanismo `merge_priors`, identificado na arquitetura do dNATY, poderá ser avaliado para
combinar informações estatísticas provenientes de diferentes dispositivos.

### Cenário proposto

Três Rovers operam em talhões diferentes:

- O Rover A observa uma determinada variedade e suas condições ambientais.
- O Rover B coleta dados em outro tipo de solo.
- O Rover C identifica variações associadas ao estágio da cultura.

Cada dispositivo produz informações locais que podem contribuir para uma representação
compartilhada.

### Fluxo operacional

1. Cada Rover coleta dados localmente.
2. As observações são validadas de acordo com as regras definidas.
3. O sistema produz estatísticas ou priores compatíveis com o protocolo de compartilhamento.
4. Os dados são enviados à Base pela rede local.
5. A Base verifica integridade, versão, origem e compatibilidade.
6. O mecanismo de fusão combina as informações aceitas.
7. O sistema avalia a atualização resultante.
8. A atualização é distribuída aos dispositivos autorizados.
9. Cada dispositivo verifica a integridade antes da utilização.

### Benefícios potenciais

- Menor dependência de conectividade externa.
- Compartilhamento de informações entre talhões.
- Atualizações locais pela rede da fazenda.
- Melhor utilização da infraestrutura Starlink.
- Possibilidade de adaptação a condições agrícolas diferentes.

**Limitação importante**: a fusão de priores não equivale automaticamente ao treinamento
federado de redes neurais. A compatibilidade estatística, a definição matemática do mecanismo
de fusão e a validação do modelo resultante precisam ser verificadas.

Além disso, o envio de poucos kilobytes é uma possibilidade de projeto, não uma garantia de
tamanho. O volume real depende da representação compartilhada.

## 7.2. Coordenação Tática entre Drone e Rover

O drone poderá realizar levantamentos em grande escala, enquanto o Rover será responsável por
inspeções detalhadas em regiões selecionadas.

**Etapa 1 — Mapeamento Aéreo.** O drone coleta imagens e informações sobre o vigor e a
estrutura do dossel. Os dados são processados para identificar regiões potencialmente
anômalas.

**Etapa 2 — Priorização de Regiões.** A Base combina os resultados com: histórico do talhão;
incidência anterior de doenças; incerteza das observações; disponibilidade dos Rovers;
condições de acesso; estado da bateria dos dispositivos.

**Etapa 3 — Inspeção Terrestre.** A Base atribui uma missão ao Rover mais adequado. O Rover
percorre a região e coleta imagens em maior resolução, permitindo uma avaliação mais
detalhada.

**Etapa 4 — Revisão e Decisão.** Os resultados são encaminhados ao sistema de análise
fitossanitária. Quando necessário, o agrônomo revisa os casos antes de autorizar qualquer
intervenção.

**Etapa 5 — Execução Controlada.** Caso exista uma operação de aplicação associada, ela
somente poderá ser executada depois das verificações agronômicas, regulatórias e de segurança
aplicáveis.

A decisão de intervenção não deve depender exclusivamente de uma classificação visual ou de
uma previsão probabilística.

## 7.3. Alocação de Missões Baseada em Incerteza

A incerteza pode ser utilizada como um dos critérios para decidir onde coletar mais
informações. Uma função de prioridade poderá combinar:

    Prioridade = f(risco fitossanitário, incerteza, impacto potencial, custo da missão,
                   disponibilidade operacional)

Essa função deve ser calibrada para evitar que o sistema envie missões excessivas para áreas
pouco relevantes ou deixe de inspecionar regiões importantes.

**Resultado esperado**: criar uma operação coordenada em que o drone identifica áreas
suspeitas, o Rover investiga os detalhes e a Base distribui as missões de forma eficiente.
