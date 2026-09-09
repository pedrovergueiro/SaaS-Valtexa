# Simulador

Uma temporada inteira em dois minutos, sem hardware nenhum.

```bash
python -m simulator
```

Sobe a plataforma num processo próprio, cria a fazenda de demonstração, provisiona
três robôs e roda o fluxo completo. Não precisa de servidor no ar, nem de banco
configurado, nem de GPU.

```bash
python -m simulator --url http://homolog.valtexa.local   # ambiente já no ar
python -m simulator --keep                               # não apaga o banco ao terminar
```

---

## Por que ele existe

Três razões, em ordem de importância:

1. **Provar a arquitetura antes do hardware.** Se o fluxo ponta a ponta não roda
   contra robôs simulados, ele não vai rodar contra robôs de verdade — só que
   descobrir isso com hardware custa meses.
2. **Ser a referência executável do protocolo.**
   [`simulator/client.py`](../simulator/client.py) é o cliente de verdade, não
   uma imitação. Quem escrever o firmware reproduz o que está ali.
3. **Provar que não existe rota privada de frontend.**
   [`simulator/operator.py`](../simulator/operator.py) faz, por HTTP, tudo que
   uma tela faria.

---

## O que o roteiro percorre

```
1. Provisionamento     três robôs geram o próprio par de chaves
                       convite reutilizado é RECUSADO

2. Varredura           missão planejada, aprovada pela segurança, assinada
                       rover verifica a assinatura antes de aceitar

3. Recarga e retomada  bateria acaba no meio -> volta -> recarrega
                       retoma SÓ com os segmentos que faltam
                       perde o enlace -> acumula -> sincroniza
                       reenvia o mesmo lote -> nada duplica

4. Diagnóstico         imagens viram diagnósticos
                       novidade separa material para o agrônomo
                       agrônomo rotula uma classe FORA do catálogo

5. Pulverização        BLOQUEADA sem aprovação do agrônomo
                       operador tenta aprovar -> 403
                       BLOQUEADA com o tanque errado
                       agrônomo aprova, tanque correto -> liberada

6. Aplicação           cerca virtual bloqueia pontos fora do polígono
                       teto de volume respeitado como teto

7. Gêmeo digital       retrato do talhão, verificação agendada, auditoria
```

**Os bloqueios são o ponto.** Um simulador que só mostra o caminho feliz não
prova nada: o valor da plataforma está exatamente no que ela recusa fazer.

---

## Como está montado

| Arquivo | O que é |
|---|---|
| `simulator/client.py` | cliente assinado do protocolo — o SDK do firmware |
| `simulator/operator.py` | cliente do lado humano |
| `simulator/devices.py` | rover, drone e dock simulados |
| `simulator/scenario.py` | o roteiro |
| `simulator/__main__.py` | sobe a plataforma e executa |

### O que os dispositivos simulados reproduzem

Não é animação: são as decisões que o firmware precisa tomar **sozinho**.

- o rover mede a própria energia e decide voltar **sem perguntar à nuvem**;
- o drone verifica a assinatura e a cerca virtual antes de abrir o bico, e fecha
  por conta própria se a trilha sair da área;
- a dock informa o vento — sem ele, a pulverização é bloqueada.

Quando o hardware existir, ele substitui `simulator/devices.py`. A nuvem não
muda.

---

## `SIMULATED_INFERENCE`

O simulador liga essa opção, que substitui os modelos por analisadores falsos e
determinísticos.

O truque: o rover monta imagens JPEG válidas com uma marca anexada ao fim do
arquivo (`VTXSIM:<rótulo>:<novidade>`). JPEG ignora bytes depois do marcador de
fim, então a etiqueta viaja junto sem corromper o arquivo, e o
`SimulatedAnalyzer` a lê para saber o que responder. A confiança vem do hash da
imagem — mesma imagem, mesma resposta, como num modelo de verdade.

É andaime de simulação e está **recusado em produção** por
`Settings.production_problems()`: um diagnóstico inventado chegando a um produtor
seria pior do que não ter diagnóstico nenhum.

Para rodar contra os modelos reais, suba o `VALTEXA-B` e use
`--url` apontando para uma plataforma com `INFERENCE_ENABLED=true`.

---

## O mesmo fluxo, em CI

[`tests/test_end_to_end.py`](../tests/test_end_to_end.py) percorre a mesma cadeia
pelo `TestClient`, sem servidor, em segundos. É a versão que roda em cada commit;
o `python -m simulator` é a versão que se mostra para uma pessoa.

---

## Credenciais da demonstração

| E-mail | Papel |
|---|---|
| `admin@valtexa.dev` | admin |
| `agronomo@valtexa.dev` | agrônomo |
| `operador@valtexa.dev` | operador |

Senha: `valtexa-demo-2026`. Fazenda `fazenda-demo`, em Itajubá (MG).

São dados de demonstração e **não devem existir em produção**. `seed_demo()` só é
chamado pelo simulador e pelos testes.

---

## O que o simulador ainda não faz

- vento e chuva variando ao longo da missão;
- falha de hardware no meio da execução (motor, sensor, câmera);
- dois robôs operando ao mesmo tempo no mesmo talhão;
- a coreografia física de acoplamento e troca de bateria na dock;
- deriva de posição — o rover simulado navega perfeitamente, o que é justamente
  o que a margem da cerca virtual existe para cobrir no mundo real.
