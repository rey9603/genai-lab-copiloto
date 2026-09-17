# Resultados del Laboratorio

## Módulo 1 — Inferencia local

### Línea base (2026-09-16, día de inauguración)
- Hardware: RTX 5080 16GB, WSL2 Ubuntu 24.04, Docker
- Servidor: vLLM 0.29.0 (VLLM_WSL2_ENABLE_PIN_MEMORY=1)
- Modelo: Qwen2.5-7B-Instruct-AWQ (4-bit), max_len 8192, gpu_util 0.85
- **Throughput: 154.8 tok/s | Latencia p50: 1.95s** (~300 tok/respuesta, 5 runs)

### Hallazgos
- FP16 7B inviable en 16GB compartida con Windows (14.3GB pesos + 1.3GB
  escritorio = sin KV cache). AWQ es config base, no optimización.
- vLLM 0.29 en WSL2 requiere VLLM_WSL2_ENABLE_PIN_MEMORY=1 (bug UVA).

### Pendiente
- [ ] vs Qwen2.5-14B-AWQ (¿más cerebro al mismo costo de VRAM?)
- [ ] vs Gemini 2.5 Flash via Vertex (latencia/calidad/costo)

### Madrugada 17-sep — 14B + Gemini conectado
- 14B-AWQ: ~55 tok/s estable, p50 ~7s (max_len 4096 + enforce-eager obligatorios:
  con CUDA graphs solo quedaban 0.12 GiB de KV; eager libera ~0.8 GiB → 4.34 GiB).
  Run 1 = cold start (7.6 tok/s): excluir warmup en benchs futuros.
- 7B vs 14B: 154.8 vs ~55 tok/s — 2× cerebro ≈ 3× costo velocidad + mitad de contexto.
- Vertex operativo: billing vinculado por CLI (proyecto nacía huérfano), Gemini 2.5
  Flash respondiendo vía ADC. Pendiente sábado: bench gemelo + calidad con golden set.
