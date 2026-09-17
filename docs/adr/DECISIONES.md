# Registro de Decisiones de Arquitectura (ADRs)

Formato: contexto → opciones consideradas → decisión → consecuencias.
Regla de la casa: **una decisión entra aquí solo si tiene datos o un trade-off explícito.**
Estado: ✅ vigente · 🔁 sustituida · 🧪 provisional (pendiente de validar con medición)

---

## ADR-001 · Plataforma: Windows + WSL2 (no Linux nativo, no dual-boot)

**Fecha:** 2026-09-16 · **Estado:** ✅

**Contexto.** El laboratorio corre en la PC personal (RTX 5080, 32 GB RAM) que también es la máquina de vida diaria y convivirá con herramientas corporativas Windows-first.

**Opciones.** (a) Linux nativo/dual-boot; (b) Windows + WSL2; (c) Windows puro.

**Decisión.** WSL2 con Ubuntu 24.04.

**Racional.**
- NVIDIA comparte el driver de Windows con WSL2 automáticamente: CUDA en contenedores funciona a ~95-98 % del rendimiento nativo, suficiente para aprendizaje e iteración.
- En hardware muy nuevo (Blackwell), los drivers de Windows suelen estar más maduros que los de distros estables.
- Se conservan ambos mundos simultáneos (VPN corporativa y Office en Windows; stack ML en Linux) sin elegir SO al arrancar.
- Windows puro se descarta: el ecosistema ML serio (vLLM, kernels CUDA, tooling) es Linux-first.

**Consecuencias.** (+) cero fricción de arranque; (+) reversible (dual-boot puede añadirse después). (−) hereda las peculiaridades de WSL2 → causaron ADR-002 y condicionan ADR-003; (−) NordVPN puede romper DNS de WSL2 (mitigación conocida: desconectar o fijar DNS).

**Configuración asociada.** `.wslconfig`: memory=24GB, processors=12, swap=16GB — contrato explícito de recursos para que la VM no compita con Windows durante cargas de modelos. Verificado desde el kernel (`free -h`, `nproc`).

---

## ADR-002 · vLLM en WSL2 requiere `VLLM_WSL2_ENABLE_PIN_MEMORY=1`

**Fecha:** 2026-09-16 · **Estado:** ✅

**Contexto.** Primer arranque de vLLM 0.29.0 murió en init con `RuntimeError: UVA is not available` (V2 Model Runner).

**Diagnóstico.** El V2 runner canaliza copias host→device por buffers UVA que requieren *pinned memory*; en WSL2 esa capacidad está desactivada por defecto (opt-in). Bug conocido upstream con dos workarounds documentados por la comunidad.

**Opciones.** (a) `VLLM_WSL2_ENABLE_PIN_MEMORY=1` (habilita pinned memory, conserva V2 runner); (b) `VLLM_USE_V2_MODEL_RUNNER=0` (degrada a runner V1); (c) fijar imagen a versión anterior.

**Decisión.** Opción (a). Verificada: el motor pasó de largo el punto de fallo y cargó el modelo.

**Consecuencias.** (+) runner moderno con mejor rendimiento; (+) en Linux nativo la variable es no-op → el mismo comando/manifiesto sirve en ambos entornos. (−) dependencia de una variable no obvia → documentada aquí y fijada en compose/manifiestos.

**Lección.** Ciclo completo de incidente de plataforma: stack trace → línea raíz → issue upstream → workaround documentado → verificación en log.

---

## ADR-003 · Cuantización AWQ como configuración base (no optimización opcional)

**Fecha:** 2026-09-16 · **Estado:** ✅

**Contexto.** Con el fix de ADR-002, Qwen2.5-7B-Instruct en BF16 cargó (14.29 GiB) pero vLLM abortó: `No available memory for the cache blocks`.

**Los números (medidos, no estimados):**

| Concepto | Valor |
|---|---|
| VRAM física RTX 5080 | 16,303 MiB |
| Reservado por Windows/escritorio (WDDM) | ~1,300 MiB |
| Disponible real para CUDA | ~14,600 MiB (el error lo confirmó: "14.6/15.89 GiB") |
| Pesos 7B en BF16 | 14,290 MiB |
| Restante para KV cache | ~380 MiB → **inviable** |
| Intento gpu_util=0.95 | pide 15.1 GiB > 14.6 disponibles → **rechazado en startup** |

**Decisión.** Servir **Qwen2.5-7B-Instruct-AWQ** (4-bit) con `--gpu-memory-utilization 0.85` y `--dtype float16`.

**Resultado.** Pesos ~5.6 GiB → ~7-8 GiB de KV cache → contexto 8K holgado. Rendimiento medido: **154.8 tok/s, p50 1.95 s**.

**Consecuencias.** (+) el sistema completo cabe con margen; (+) throughput excelente para uso interactivo. (−) pérdida de precisión propia de 4-bit (típicamente baja; **pendiente cuantificarla** con la suite del M3 → ADR futura). 

**Principio destilado.** En GPU de 16 GB compartida con el escritorio, la VRAM se reparte entre *pesos* y *memoria de trabajo* (KV cache): la cuantización no es ahorro, es lo que permite que exista el sistema completo.

---

## ADR-004 · Modelo generador base: Qwen2.5-7B-Instruct (familia Qwen)

**Fecha:** 2026-09-16 · **Estado:** 🧪 (retar con 14B-AWQ y comparativo cloud)

**Contexto.** Elegir el LLM local inicial del laboratorio.

**Opciones.** Llama-3.1-8B (licencia gated + token), Mistral-7B, Gemma-9B, Qwen2.5-7B.

**Decisión.** Qwen2.5-7B-Instruct.

**Racional.** Top de su clase 7-9B en benchmarks públicos; español fuerte (relevante para un copiloto en español); licencia Apache 2.0 sin fricción de descarga; disponibilidad de variantes AWQ oficiales y de tamaños 14B/32B para escalar el comparativo.

**Plan de validación.** Benchmark 7B-AWQ vs 14B-AWQ (¿más capacidad al mismo costo de VRAM?) y vs Gemini 2.5 Flash (calidad/latencia/costo) con el golden set del M3.

---

## ADR-005 · Serving con vLLM y API estilo OpenAI (no Ollama/llama.cpp)

**Fecha:** 2026-09-16 · **Estado:** ✅

**Contexto.** Elegir el servidor de inferencia local.

**Opciones.** (a) Ollama (simplicidad de escritorio); (b) llama.cpp server; (c) vLLM.

**Decisión.** vLLM.

**Racional.**
- Es el estándar de *producción*: continuous batching, PagedAttention (gestión de KV cache), selección automática de kernels (eligió FlashAttention 2 para Blackwell), métricas Prometheus en `/metrics`. El objetivo del laboratorio es practicar el stack industrial, no el de escritorio.
- **API compatible OpenAI** → todo el código cliente funciona igual contra local, Vertex, o cualquier proveedor cambiando URL/credenciales. Es la pieza que hace posible el *router de modelos* (M1) sin reescrituras.

**Consecuencias.** (+) transferencia directa a entornos reales; (+) benchmark honesto contra APIs comerciales. (−) más pesado y quisquilloso que Ollama (la imagen pesa ~10 GB; sufrimos ADR-002/003) — precio aceptado por valor de aprendizaje.

---

## ADR-006 · Corpus de dominio 100 % sintético

**Fecha:** 2026-09-16 · **Estado:** ✅ (principio innegociable)

**Contexto.** El copiloto necesita un corpus bancario; el autor trabaja/trabajará en instituciones reales.

**Decisión.** Todo el corpus (políticas POL-x.x, clientes de las tools, casos del golden set) es **generado sintéticamente**. Ningún documento, dato o artefacto de empleador presente o futuro entra al laboratorio; el conocimiento portable son patrones y metodología, nunca material.

**Consecuencias.** (+) cero riesgo legal/ético; (+) el corpus se diseña a la medida de lo que cada módulo necesita enseñar (ambigüedades deliberadas para retar al RAG, políticas en tensión para retar al agente). (−) los resultados no reflejan la mugre de datos reales — se compensa inyectando ruido y casos borde a propósito.

---

## ADR-007 · Nube de comparación: Vertex AI (GCP)

**Fecha:** 2026-09-16 · **Estado:** ✅

**Contexto.** El laboratorio necesita un "brazo cloud" para el comparativo local-vs-API, segundo juez de evaluación y, más adelante, tuning gestionado.

**Opciones.** (a) solo APIs directas (OpenAI/Anthropic); (b) AWS Bedrock; (c) Vertex AI.

**Decisión.** Vertex AI como plataforma cloud principal (proyecto `copiloto-lab`), complementada con APIs de Anthropic/OpenAI para el rol de jueces premium en evaluación.

**Racional.** Vertex aparece nombrado en el stack objetivo del rol profesional → valor directo de familiaridad; da acceso a Gemini y Model Garden con un free tier/credits suficientes para el volumen del laboratorio; presupuesto con alertas configurado ($10 USD) como control de gasto.

**Consecuencias.** (+) alineación con el stack del trabajo real; (+) el router de M1 nace multi-proveedor. (−) un proveedor cloud más que administrar; mitigado por volumen mínimo y facturación post-pago con alertas.

---

## ADR-008 · Kubernetes al final (M7), no al principio

**Fecha:** 2026-09-16 · **Estado:** ✅

**Contexto.** Tentación natural de arrancar con K8s (aparece en el perfil objetivo).

**Decisión.** Desarrollo con `docker run`/`docker compose`; K8s entra como módulo de cierre con k3d, cuando exista un sistema multi-servicio que orquestar.

**Racional.**
- Un cluster vacío no enseña nada; el mismo cluster con el copiloto completo enseña todo (Deployments, Services, ConfigMaps —formalización del patrón `-e` ya usado—, HPA, probes —formalización del `/health` ya probado—).
- GPU passthrough dentro de k3d sobre WSL2 es el rincón más frágil del stack; se pospone la fricción hasta que compre aprendizaje. Alternativa pedagógica: orquestar primero los servicios sin GPU (API, Qdrant, Langfuse) dejando vLLM fuera del cluster.
- Antecedente personal: el pipeline doctoral ya corre en K8s → el objetivo aquí es *entender* la traducción compose→manifiestos, no descubrir K8s desde cero.

**Consecuencias.** (+) foco en el corazón GenAI (RAG/agentes/evals) primero. (−) el despliegue declarativo llega tarde; aceptado conscientemente.

---

## Plantilla para nuevas ADRs

```
## ADR-XXX · Título

**Fecha:** · **Estado:** 🧪/✅/🔁

**Contexto.** Qué problema o elección apareció.
**Opciones.** Las alternativas reales consideradas.
**Decisión.** Qué se eligió.
**Racional.** Por qué — con números si existen.
**Consecuencias.** Lo bueno Y lo malo que se acepta.
```

### ADRs previsibles del backlog
- ADR-009: estrategia de chunking del corpus (fijo vs semántico vs estructural) — con métricas de retrieval (M2).
- ADR-010: embedder (bge-m3 local vs text-embedding de Gemini) — costo/calidad (M2).
- ADR-011: fusión de retrieval (RRF vs pesos) y elección de reranker (M2).
- ADR-012: rúbrica y modelo del LLM-as-judge + resultado de calibración contra juicio humano (M3).
- ADR-013: política del router (qué consultas escalan a API y por qué) — con distribución medida (M1/M4).
- ADR-014: fine-tune vs RAG vs híbrido — resultado del experimento (M5).
