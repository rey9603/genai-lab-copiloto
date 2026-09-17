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
