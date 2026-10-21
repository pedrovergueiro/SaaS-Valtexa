# Estado atual da ValTexa

> Atualizado em 20/10/2026, depois da consolidação. Números **medidos** (fora da amostra, salvo
> indicação). Onde algo não foi testado em hardware ou em campo, está dito.
> Arquitetura: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Em uma frase

Plataforma autônoma de lavoura com **foco no café do Sul de Minas**. O ciclo completo
(Rover fotografa → IA embarcada prioriza → IA na nuvem diagnostica e funde por planta →
plataforma monta mapa, incidência, previsão e prescrição → agrônomo aprova → Safety Engine
autoriza → aplicação → verificação) **roda inteiro em simulação e com os pesos reais**.
**Nada rodou no Rover real e não houve piloto de campo.**

## Comunicação

Cada Rover tem a **própria Starlink** e fala com a plataforma por HTTPS direto. A base da
fazenda e o rádio foram **arquivados** em 20/10/2026 (nunca rodaram em hardware).

## IA (VALTEXA-B)

| Modelo | Cultura | Estado | Números |
|---|---|---|---|
| `coffee-foliar` | **Café** | treinado | CNN sozinha: teste 0,950, mas 6,5% num conjunto externo. Com **SigLIP 2 + cabeça**: isolado 0,964, **externo 0,801**, BRACOL 0,914 |
| `banana-foliar` | Banana | treinado | campo 0,829 · teste 0,977 |
| `citrus-foliar` | Citros | treinado | campo 0,969 · teste 0,884 |
| `leaf-foliar` | Milho | treinado | teste 0,956 |
| `rover-understory` | Milho | quarentena | aprendeu a sessão de fotografia, não a doença |

- **Aprendizado contínuo** com portão: BRACOL 0,300 → 0,847; alarme falso em sadias 100% → 0%;
  externo 0,165 → 0,841. O portão reprovou 9/9 rodadas ingênuas.
- **Fusão por planta calibrada** (a oficial): banana 115/125 plantas com 15/283 alarmes falsos;
  citros 33/33 (alarme falso de citros em árvore real **não medido**).
- **Gêmeo digital** por planta (SEIR, clima, vento, previsão, prioridades por valor da
  informação): validado em dado **sintético**; nada medido em campo.

## Rover (VALTEXA-ROVER)

- Edge AI do café: SigLIP + cabeça em ONNX, igual à nuvem (diferença máx. 1,6e-5). CPU:
  ~131 ms por recorte, ~9,8 s por quadro de 70 recortes. **Jetson não medida.**
- Mosaico de café fora da amostra: plantas priorizadas 160/240 com 5% de incidência,
  240/240 com 10% e 20%; quadros sadios que viram evento 11,4%.
- Percepção ativa, RGB-D, geometria da folha, qualidade/conformal/novidade por recorte,
  orçamento de dados da Starlink, vídeo ao vivo, OTA com hash e procedência.
- Adapters do Rover V3 (OAK-D, ZED-F9P, Xsens, navegação por arquivo) **nunca rodaram no
  hardware**; o protocolo com a navegação/MCU não está definido do lado da navegação.

## Plataforma (VALTEXA-SAAS)

Multi-tenant, frota, missões assinadas, decisão determinística, aprovação do agrônomo,
Safety Engine, mapa de aplicação localizada, validação de campo, enxame (só rascunhos),
cérebro agronômico (LLM desligado), observabilidade, OTA, console web, simulador.
Produção: `deploy/` pronto, **nunca implantado de verdade**.

## Testes (20/10/2026, depois da consolidação)

| Projeto | Resultado |
|---|---|
| IA | 859 passam, 5 pulados (WSL); ruff 0.6.9: só os 5 avisos do terreno em andamento |
| Plataforma | 1.085 passam, 9 pulados (suíte completa ~18 min); ruff limpo |
| Console web | 153 testes, `tsc` e build ok |
| Rover | 303 passam + 3 pulados (Windows); 294 + 12 pulados no Python 3.10 da Jetson |

## Limitações conhecidas

1. Nenhum hardware real rodou; não há fotos de café na escala do Rover nem piloto de campo.
2. **Erros confiantes**: doença fora do catálogo passa como diagnóstico confiante em ~81% dos
   casos; em vídeos do YouTube quase tudo virava "ferrugem" (o portão "cena vencedora é
   folha" corrigiu parte); a novidade não pega erro confiante em folha. Por isso existem a
   validação humana e o Safety Engine.
3. **Licença**: a cabeça do café foi treinada com o dNATY, de licença **não comercial**.
4. A prevalência por EM do talhão não é confiável (marcada); a incidência por planta é a oficial.
5. Google Maps sem faturamento; imagem Esri só em demonstração local.
6. Depois de promover uma cabeça nova, o conformal precisa ser recalibrado.
7. Boa parte do trabalho das rodadas 4 e 5 e toda a consolidação **não estão commitadas**.

## Próximos passos reais

1. Montar o Rover V3 e rodar `valtexa-rover diagnostico` (câmeras, GNSS, IMU, tempo na Jetson,
   profundidade).
2. Piloto em talhão de café: quadros na escala do Rover, rótulo do agrônomo por planta,
   recalibrar a regra de borda e a fusão com dados reais; medir a Starlink sob o dossel.
3. Resolver a licença da cabeça do café (dNATY) antes de uso comercial.
4. Definir o protocolo com a navegação/MCU e a regra de voo de observação do drone.
5. Commitar o trabalho local (rodadas 4–5 e consolidação) em cada repositório.
