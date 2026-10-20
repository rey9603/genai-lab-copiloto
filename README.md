# Laboratorio GenAI — Copiloto Bancario

**Autor:** Raimer Salas González
**Inicio:** 16 de septiembre de 2026
**Propósito:** Laboratorio personal de aprendizaje que replica, de punta a punta, RAG de grado empresarial, agentes, evaluación sistemática, gobernanza, observabilidad y orquestación. Cada módulo cubre una capacidad real del dominio **haciéndola**, y cada decisión técnica queda documentada con datos en un ADR.

> Este laboratorio es personal y corre en hardware propio. No contiene datos, código ni información de ningún empleador. El dominio bancario se simula con un corpus de políticas **sintéticas**.

---

## 1. Visión

Construir un **copiloto de políticas bancarias**: un asistente que responde preguntas operativas (crédito, prevención de fraude, cumplimiento simulado) citando las políticas que fundamentan cada respuesta, capaz de escalar a razonamiento agéntico cuando la consulta lo requiere, con evaluación automática de calidad, guardrails de seguridad, observabilidad de costos/latencia, y despliegue reproducible.

El sistema es el vehículo; el objetivo real es el **criterio**: saber, con números propios, cuándo un modelo local basta y cuándo pagar API, cómo se mide la calidad de un RAG, cómo se evalúa un agente, cuándo conviene fine-tuning, y cómo se ve "gobernado y observable" en código.

## 2. Arquitectura

### 2.1 Diagrama general

```
┌─────────────────────────────────────────────────────────────────┐
│  HOST: PC personal · RTX 5080 16GB · WSL2 Ubuntu 24.04 · Docker │
│                                                                 │
│   USUARIO ──► API COPILOTO (FastAPI)                            │
│                    │                                            │
│         ┌──── GUARDRAILS de entrada ────────────┐               │
│         │  (PII/Presidio, jailbreak, temas      │               │
│         │   prohibidos)                         │               │
│         ▼                                       │               │
│    ┌─ AGENTE (LangGraph) ─────────────┐         │               │
│    │  razonamiento multi-paso         │    OBSERVABILIDAD       │
│    │  tools: buscar_politica,         │    (Langfuse:           │
│    │         calcular_riesgo,         │     trazas, costos,     │
│    │         consultar_cliente_mock   │     latencias por       │
│    │  decisión: responder / escalar   │     etapa)              │
│    └──────┬───────────────────────────┘         ▲               │
│           ▼                                     │               │
│    ┌─ RAG CORE ─────────────────────────┐       │               │
│    │  retrieval híbrido (denso + BM25)  │───────┘               │
│    │  + reranker → generación           │                       │
│    │  → respuesta CON CITAS [POL-x.x]   │                       │
│    └──┬──────────────────────────┬──────┘                       │
│       ▼                          ▼                              │
│  ┌─ QDRANT ─────────┐   ┌─ ROUTER DE MODELOS ────────────────┐  │
│  │ vector DB        │   │ 1) vLLM local (Qwen AWQ) — $0      │  │
│  │ corpus POL-x.x   │   │ 2) Vertex AI / Gemini — cloud $    │  │
│  │ (sintético)      │   │ 3) Claude / GPT — premium, jueces  │  │
│  └──────────────────┘   └────────────────────────────────────┘  │
│                                                                 │
│  ┌─ EVALUACIÓN (capa transversal) ─────────────────────────┐    │
│  │ golden dataset · métricas de retrieval · LLM-as-judge   │    │
│  │ calibrado · suite de regresión (CI)                     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─ ORQUESTACIÓN Y DESPLIEGUE (fase final) ────────────────┐    │
│  │ Airflow (ingesta y evals programados) · K8s local (k3d) │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Capas del sistema

| Capa | Componente | Tecnología | Rol |
|---|---|---|---|
| Serving | Servidor de inferencia | vLLM (Docker) | Sirve el LLM local con API compatible OpenAI |
| Modelo | LLM generador | Qwen2.5-7B-Instruct-AWQ | Generador base, cuantizado 4-bit |
| Conocimiento | Base vectorial | Qdrant (Docker) | Almacena embeddings del corpus con metadata filtrable |
| Recuperación | RAG core | Python (FastAPI) | Retrieval híbrido + rerank + generación con citas |
| Razonamiento | Agente | LangGraph | Tool calling, multi-paso, decisión responder/escalar |
| Calidad | Evaluación | Golden set + LLM-as-judge | Métricas de retrieval y generación; regresión en CI |
| Seguridad | Guardrails | Presidio + reglas | Filtrado de PII, jailbreak, temas prohibidos |
| Operación | Observabilidad | Langfuse (self-hosted) | Trazas, costos por request, latencia por etapa |
| Nube | Proveedor externo | Vertex AI (GCP `copiloto-lab`) | Comparativo cloud, segundo juez, tuning gestionado |
| Infra | Orquestación | Airflow + k3d (K8s) | Pipelines programados y despliegue declarativo |

### 2.3 Flujo de una consulta (camino feliz)

1. Usuario envía pregunta → **API**.
2. **Guardrails de entrada**: se filtra PII, se detecta jailbreak/temas prohibidos; si algo dispara, se responde con negativa controlada y se registra.
3. **Agente** decide: ¿consulta simple (directo a RAG) o requiere herramientas/razonamiento multi-paso?
4. **RAG**: la consulta se convierte a embedding; Qdrant devuelve candidatos (denso) que se fusionan con BM25 (léxico); el **reranker** ordena; los top-k chunks van al prompt.
5. **Router** elige el modelo según política (default: local; escalamiento a API según complejidad/config).
6. Generación **con citas obligatorias** `[POL-x.x]`; si el contexto no sustenta la respuesta, el sistema lo dice (no inventa).
7. **Guardrails de salida** + registro completo en **Langfuse** (prompt, contexto, respuesta, tokens, costo, latencia por etapa).

## 3. Estructura del repositorio

```
~/lab/copiloto-bancario/
├── README.md                  # este documento
├── RESULTADOS.md              # bitácora de mediciones
├── docker-compose.yml         # stack local: vllm + qdrant + langfuse
├── .env.example               # variables (HF_TOKEN, llaves API) — nunca commitear .env
├── corpus/                    # políticas bancarias SINTÉTICAS (POL-x.x en Markdown)
├── src/
│   ├── bench.py               # benchmark de inferencia (throughput/latencia)
│   ├── ingesta/               # chunking + embeddings + carga a Qdrant
│   ├── rag/                   # retrieval híbrido, rerank, generación con citas
│   ├── agente/                # LangGraph: grafo, tools, contratos
│   ├── router/                # clientes conmutables: local / vertex / anthropic
│   └── guardrails/            # filtros de entrada/salida
├── evals/
│   ├── golden/                # dataset de casos con respuestas esperadas
│   ├── judge/                 # rúbricas y calibración del LLM-as-judge
│   └── regression/            # suite ejecutable en CI
├── k8s/                       # manifiestos (fase final)
└── docs/
    └── adr/                   # decisiones de arquitectura numeradas
```

## 4. Módulos del programa

| # | Módulo | Estado | Pregunta que responde |
|---|---|---|---|
| M1 | Inferencia local y router de modelos | 🟡 En curso (base medida) | ¿Cuándo basta el modelo local y cuándo pagar API? |
| M2 | RAG empresarial | ⬜ Siguiente | ¿Qué decisiones de chunking/retrieval mueven las métricas y cuánto? |
| M3 | Evaluación sistemática | ⬜ | ¿Cómo sé que un cambio mejoró el sistema sin leer 100 respuestas? |
| M4 | Agentes y su evaluación | ⬜ | ¿Cómo se evalúa y gobierna un agente, no solo un chat? |
| M5 | Fine-tuning (QLoRA) | ⬜ | Fine-tune vs RAG vs ambos: ¿qué gana, medido? |
| M6 | Gobernanza y observabilidad | ⬜ | ¿Cómo se ve "gobernado y observable" en código? |
| M7 | Orquestación (Airflow + K8s) | ⬜ | ¿Cómo se industrializa: del compose al cluster? |

El detalle de alcance, entregables y criterios de éxito por módulo está en `docs/MODULOS.md`.

## 5. Estado actual y línea base

**Conquistado (16-sep-2026):**
- Rig operativo: WSL2 + Docker + GPU passthrough certificado en contenedor.
- vLLM 0.29.0 sirviendo **Qwen2.5-7B-Instruct-AWQ**: **154.8 tok/s, p50 1.95 s** (5 runs, ~300 tok/respuesta).
- GCP: proyecto `copiloto-lab` con Vertex AI API habilitada; presupuesto con alertas.
- Hallazgos registrados: ADR-001 (WSL2 como plataforma), ADR-002 (pin memory), ADR-003 (AWQ obligatorio en 16 GB).

**Backlog inmediato:** HF_TOKEN en el entorno · descarga de Qwen2.5-14B-AWQ para comparativo · script gemelo de bench contra Gemini (Vertex) · `docker-compose.yml` del stack M2.

## 6. Principios de trabajo

1. **Diagnóstico barato antes de construcción cara** — probar el eslabón pequeño (imagen CUDA de 100 MB) antes del grande (vLLM de 10 GB).
2. **Toda decisión con números** — si no hay medición, es opinión; las opiniones no van a los ADRs.
3. **Dimensionar antes de construir** — no aeropuertos para paradas de autobús; cada módulo entra cuando hay algo que lo justifique.
4. **Separación estricta personal/corporativo** — el laboratorio vive en hardware propio; conocimiento portable sí, artefactos de empleadores jamás.
5. **Reproducibilidad** — todo en contenedores, configuración por entorno, secretos fuera del repo.
6. **El laboratorio sigue al trabajo real** — los módulos se profundizan según lo que el rol demande.
