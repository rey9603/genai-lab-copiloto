# Plan de Módulos — alcance, entregables y criterios de éxito

Cada módulo responde una pregunta de ingeniería/negocio y termina con: (1) algo funcionando, (2) mediciones en `RESULTADOS.md`, (3) al menos una ADR si hubo decisión con trade-off.

---

## M1 · Inferencia local y router de modelos — 🟡 en curso

**Pregunta:** ¿cuándo basta el modelo local ($0) y cuándo se justifica la API de pago?

**Hecho:** rig certificado; vLLM + Qwen2.5-7B-AWQ sirviendo; línea base **154.8 tok/s / p50 1.95 s**; `src/bench.py`.

**Por hacer:**
- [ ] `HF_TOKEN` en entorno (descargas rápidas y modelos gated).
- [ ] Benchmark **Qwen2.5-14B-Instruct-AWQ** (~10 GB): ¿más capacidad, qué costo en tok/s y VRAM?
- [ ] Cliente Vertex (`google-genai`) + bench gemelo contra **Gemini 2.5 Flash**: latencia, throughput percibido, **costo por 1K consultas**.
- [ ] `src/router/`: cliente conmutable `local | vertex | anthropic` bajo una interfaz común (posible gracias a la API estilo OpenAI — ADR-005), con logging de costo/latencia por request.

**Criterio de éxito:** tabla comparativa 7B-local vs 14B-local vs Gemini con las tres dimensiones (calidad cualitativa preliminar, velocidad, costo) + ADR-013 borrador de política de routing.

---

## M2 · RAG empresarial — ⬜ siguiente (fin de semana)

**Pregunta:** ¿qué decisiones de chunking/retrieval mueven las métricas, y cuánto?

**Alcance:**
1. **Corpus sintético** (`corpus/`): ~10 políticas bancarias en Markdown con identificadores `POL-x.x` — crédito, fraude, PLD simulado, atención a clientes — con ambigüedades y tensiones deliberadas (material de reto para M3/M4).
2. **`docker-compose.yml`**: vllm + qdrant (+ langfuse desde ya, aunque M6 lo explote) — el stack se levanta con un comando.
3. **Ingesta** (`src/ingesta/`): parser de Markdown → chunking comparado (tamaño fijo vs por estructura de secciones) → embeddings → carga a Qdrant con metadata (política, sección, versión).
4. **Embedder:** bge-m3 local (conocido, corre en GPU) vs text-embedding de Gemini — comparar costo/calidad → ADR-010.
5. **Retrieval híbrido:** denso (Qdrant) + léxico (BM25) con fusión RRF; reranker (bge-reranker en GPU) → ADR-011.
6. **Generación con citas obligatorias:** prompt que exige `[POL-x.x]` por afirmación y "no encontrado en políticas" cuando el contexto no sustenta (anti-alucinación por diseño).
7. Endpoint `POST /ask` en FastAPI.

**Criterio de éxito:** preguntas de prueba respondidas con citas correctas; medición inicial de retrieval (hit-rate@k manual sobre ~20 preguntas); ADR-009/010/011 con datos.

---

## M3 · Evaluación sistemática — ⬜ (el diferenciador)

**Pregunta:** ¿cómo sé que un cambio mejoró el sistema sin leerme 100 respuestas?

**Insumos:** metodologías de la sesión de intercambio con QA (golden datasets, LLM-as-judge, regresiones, herramientas, "qué no funcionó").

**Alcance:**
1. **Golden dataset** (`evals/golden/`): 50-100 casos {pregunta, chunks esperados, respuesta de referencia, categoría} — incluye casos borde: preguntas sin respuesta en el corpus, ambiguas, multi-política.
2. **Métricas de retrieval:** hit-rate@k, MRR — ¿llegó el contexto correcto?
3. **LLM-as-judge** (`evals/judge/`): rúbrica explícita (fidelidad al contexto, corrección de citas, completitud, formato); juez premium (Claude/GPT) + **segundo juez** (Gemini) para medir acuerdo inter-juez.
4. **Calibración del juez:** etiquetar a mano ~30 casos y medir acuerdo juez-vs-humano; si <85 %, iterar rúbrica → ADR-012.
5. **Suite de regresión** (`evals/regression/`): ejecutable con un comando; en GitHub Actions si el repo se publica. Todo cambio de prompt/modelo/índice corre la suite.

**Criterio de éxito:** poder afirmar "el cambio X movió faithfulness de A→B y hit-rate de C→D" para cualquier cambio del sistema.

---

## M4 · Agentes y su evaluación — ⬜

**Pregunta:** ¿cómo se evalúa y gobierna un agente, no solo un chat?

**Alcance:**
1. **Grafo LangGraph** (`src/agente/`): nodo de decisión (¿RAG directo o herramientas?) → tools → síntesis → decisión final **responder / escalar a humano**.
2. **Tools (3):** `buscar_politica` (envuelve el RAG), `calcular_riesgo` (función determinista sobre reglas sintéticas), `consultar_cliente_mock` (base de clientes ficticios).
3. **Evaluación de trayectorias:** checks de contrato sobre el camino, no solo la respuesta — ¿usó las tools correctas?, ¿en orden razonable?, ¿respetó el formato?, ¿escaló cuando las políticas estaban en tensión? (patrón heredado del eval harness del proyecto de detección de fraude).
4. **Multiagente mínimo:** investigador + redactor, para tocar coordinación entre agentes.

**Criterio de éxito:** suite de contratos de agente en verde; casos de escalamiento correcto ante políticas en conflicto; trazas completas en Langfuse.

---

## M5 · Fine-tuning con QLoRA — ⬜ (el que la GPU propia permite)

**Pregunta:** fine-tune vs RAG vs híbrido — ¿qué gana, medido?

**Alcance:**
1. Dataset de instrucciones del dominio: 500-1000 pares Q&A generados desde el corpus (sintético sobre sintético) + curados a mano.
2. **QLoRA** con Unsloth sobre un 7-8B en la 5080 (entrenamiento en horas; checkpoints en disco — presupuestar ~10-20 GB).
3. Evaluar las tres configuraciones **con la suite del M3** (por eso M5 va después): base+RAG vs fine-tuned solo vs fine-tuned+RAG.
4. Comparativo conceptual con el tuning gestionado de Vertex (qué abstrae, qué cuesta).

**Criterio de éxito:** ADR-014 con la respuesta empírica y sus números — la decisión de negocio #1 de GenAI empresarial, resuelta en el propio laboratorio.

---

## M6 · Gobernanza y observabilidad — ⬜

**Pregunta:** ¿cómo se ve "gobernado y observable" en código, no en slides?

**Alcance:**
1. **Langfuse** explotado a fondo: trazas por etapa (guardrails→agente→retrieval→generación), costo por consulta, dashboards de latencia.
2. **Guardrails de entrada** (`src/guardrails/`): PII con **Presidio** (detección/anonimización), heurísticas de jailbreak, lista de temas prohibidos.
3. **Guardrails de salida:** verificación de citas presentes, filtrado de PII residual.
4. **Audit log** estilo bancario: quién preguntó qué, qué contexto se usó, qué modelo respondió, inmutable y consultable.

**Criterio de éxito:** demo de ataque bloqueado (prompt injection / extracción de PII) con su traza; tablero de costos respondiendo "¿cuánto costó cada consulta y dónde se fue el tiempo?".

---

## M7 · Orquestación: Airflow + Kubernetes — ⬜ (graduación)

**Pregunta:** ¿cómo se industrializa — del compose al cluster?

**Alcance:**
1. **Airflow**: DAG de ingesta (detectar políticas nuevas/cambiadas → re-chunk → re-embed → upsert a Qdrant) y DAG nocturno de evals (correr suite M3 → publicar métricas).
2. **K8s local con k3d** (ADR-008): manifiestos en `k8s/` — Deployments (API, Qdrant como StatefulSet, Langfuse), Services, ConfigMaps/Secrets (formalización del patrón `-e`), probes (formalización de `/health`), HPA para la API. vLLM: primero fuera del cluster (GPU passthrough en k3d/WSL2 es frágil); dentro solo si la fricción se justifica.
3. ADR de cierre: qué cambió del compose al cluster y qué costó.

**Criterio de éxito:** `kubectl get all` mostrando el sistema vivo; matar un pod y verlo renacer; un cambio de config desplegado sin downtime.

---

## Calendario realista

| Ventana | Foco |
|---|---|
| Semana del 16-sep (transición laboral) | Solo postres: HF_TOKEN, descarga 14B-AWQ |
| Fin de semana 19-20 sep | **M2 completo** + conexión Vertex (bench gemelo) |
| Semana 1 en el nuevo rol | **M3**: golden set + primer judge (noches ligeras) |
| Semanas 2-4 | **M4** + cierre de M1 (comparativo completo) |
| Mes 2+ | M5 → M6 → M7, al ritmo que la vida permita 👶 |

El calendario es orientativo; la regla fija es la secuencia M2→M3 (la evaluación necesita algo que evaluar) y M3 antes de M5 (el experimento de fine-tuning se mide con la suite).
