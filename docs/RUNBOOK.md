# Runbook de Operación del Laboratorio

Guía de operación diaria: arrancar, verificar, monitorear, apagar y destrabar.

## 1. Arquitectura de ejecución (dónde vive cada cosa)

```
Windows (host) ── driver NVIDIA 616.92 ── RTX 5080 (16 GB)
  └── WSL2: Ubuntu-24.04 (usuario: raimer · 24 GB RAM · 12 cores · swap 16 GB)
        └── Docker Desktop (backend WSL2, integración Ubuntu-24.04 ON)
              └── contenedor `vllm` → puerto 8000 (accesible también desde Windows)
Cache de modelos:  ~/.cache/huggingface/hub/models--{org}--{modelo}/
Proyecto:          ~/lab/copiloto-bancario/
```

**Reglas de oro heredadas del setup:**
- Drivers NVIDIA **solo en Windows**, nunca dentro de Ubuntu (se comparten solos).
- El código vive **dentro** del filesystem de WSL (`~/lab/...`), no en `/mnt/c/...` (I/O cruzado es lento).
- Archivos de Linux se editan desde Linux (nano hoy; VS Code + extensión WSL como cockpit definitivo).

## 2. Arranque y apagado

```bash
# Entrar al laboratorio (desde PowerShell):
wsl ~

# ¿El contenedor vllm existe / corre?
docker ps -a

# Arrancarlo si está detenido (arranque en caliente: ~30-60 s, todo cacheado):
docker start vllm && docker logs -f vllm     # esperar "Application startup complete"

# Crearlo desde cero (si no existe) — comando canónico:
docker run -d --name vllm --gpus all -p 8000:8000 \
  -e VLLM_WSL2_ENABLE_PIN_MEMORY=1 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-7B-Instruct-AWQ \
  --max-model-len 8192 --gpu-memory-utilization 0.85 \
  --dtype float16

# Apagar (libera ~6 GB de VRAM):
docker stop vllm
```

> El contenedor es independiente de las terminales: sobrevive a cerrarlas. Muere solo con `docker stop`, al cerrar Docker Desktop o al apagar la PC.

## 3. Verificaciones (smoke tests)

```bash
# Cadena GPU completa (el "multímetro" — úsalo tras actualizar driver/Docker):
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi

# ¿Servidor vivo?
curl -s http://localhost:8000/health && echo OK

# ¿Modelo cargado y cuál?
curl -s http://localhost:8000/v1/models | python3 -m json.tool

# Prueba funcional mínima:
curl -s http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen2.5-7B-Instruct-AWQ","messages":[{"role":"user","content":"ping"}],"max_tokens":10}'

# Benchmark de referencia (comparar contra línea base 154.8 tok/s):
python3 ~/lab/copiloto-bancario/src/bench.py
```

## 4. Monitoreo

```bash
watch -n 2 nvidia-smi          # VRAM/uso GPU en vivo (esperado en reposo: ~7 GB ocupados por vllm)
docker stats vllm --no-stream  # CPU/RAM/red del contenedor
docker logs vllm --tail 50     # últimas líneas del servidor
curl -s http://localhost:8000/metrics | head -40   # métricas Prometheus de vLLM
df -h / && du -sh ~/.cache/huggingface/hub/*       # disco WSL y peso por modelo
```

**Interpretación rápida de logs de arranque:** `Loading safetensors ... 4/4` (pesos a RAM) → `Model loading took X GiB` (a VRAM) → `torch.compile` + `Capturing CUDA graphs` (warmup, cacheado tras la primera vez) → `Application startup complete` (listo).

## 5. Gestión de modelos

```bash
ls ~/.cache/huggingface/hub/                                  # modelos descargados
du -sh ~/.cache/huggingface/hub/models--Qwen--*               # peso de cada uno
# Cambiar de modelo = recrear contenedor con otro --model (el cache evita re-descargas):
docker stop vllm && docker rm vllm && docker run ... --model <nuevo>
# Borrar un modelo:
rm -rf ~/.cache/huggingface/hub/models--{org}--{modelo}
```

Presupuesto de VRAM (16 GB − ~1.3 GB de Windows ≈ 14.6 GB útiles): pesos + KV cache deben caber en `total × gpu-memory-utilization`. Referencias: 7B-AWQ ≈ 5.6 GB, 14B-AWQ ≈ 10 GB, 7B-FP16 ≈ 14.3 GB (inviable aquí, ADR-003).

## 6. Troubleshooting (los que ya nos pasaron + los previsibles)

| Síntoma | Causa probable | Remedio |
|---|---|---|
| `RuntimeError: UVA is not available` | Pinned memory off en WSL2 (ADR-002) | `-e VLLM_WSL2_ENABLE_PIN_MEMORY=1` |
| `No available memory for the cache blocks` | Pesos + Windows no dejan KV cache (ADR-003) | Modelo AWQ, o bajar `--max-model-len`, o cerrar apps que usen GPU |
| `Free memory ... less than desired` en startup | `gpu-memory-utilization` pide más de lo libre | Bajar a 0.85; verificar consumo de Windows con `nvidia-smi` en PowerShell |
| Descargas fallan / DNS raro en WSL | NordVPN rompe resolución de WSL2 | Desconectar VPN y reintentar; fix permanente: DNS fijo en `/etc/wsl.conf` |
| `docker: command not found` en Ubuntu | Integración WSL apagada o sesión vieja | Docker Desktop → Resources → WSL Integration → Ubuntu ON; reabrir terminal |
| `nvidia-smi` falla en Ubuntu | Driver Windows viejo o WSL desactualizado | Actualizar driver en Windows; `wsl --update`; nunca instalar drivers en Ubuntu |
| Pantalla negra al actualizar driver NVIDIA | Conflicto con segundo monitor | Desconectar monitor secundario → instalar → reconectar |
| Log de vLLM "quieto" durante descarga | El progreso no se imprime; va a archivos `.incomplete` | Verificar con `du -sh` del directorio del modelo o `docker stats` (NET I/O) |
| C: de Windows no recupera espacio al borrar en Ubuntu | El `.vhdx` crece pero no encoge | `wsl --shutdown` + `wsl --manage Ubuntu-24.04 --set-sparse true` |
| Pegado multilínea se desordena en PowerShell | Heredocs/continuaciones son sintaxis bash | Comandos del lab siempre dentro de `wsl`; en PowerShell usar cmdlets nativos |

## 7. Higiene y seguridad

- **Espacio:** `docker system df` (qué acumula Docker) · `docker system prune` (huérfanos) · vigilar C: con `Get-PSDrive C` en PowerShell.
- **Secretos:** `.env` local (HF_TOKEN, llaves de Vertex/Anthropic) fuera de git — `.env.example` como plantilla. Nunca llaves en comandos que queden en el historial de shell.
- **GCP:** presupuesto con alertas ($10 USD) en `copiloto-lab`; revisar Billing tras sesiones intensas de API.
- **Separación:** este laboratorio no toca equipos ni redes corporativas; máquina personal, corpus sintético (ADR-006).

## 8. Referencia de puertos y rutas

| Recurso | Dónde |
|---|---|
| API vLLM (OpenAI-style) | `http://localhost:8000/v1/...` (visible desde Ubuntu y Windows) |
| Health / modelos / métricas | `/health` · `/v1/models` · `/metrics` |
| Próximos (M2/M6) | Qdrant `:6333` · Langfuse `:3000` · API copiloto `:8080` (por compose) |
| Proyecto / corpus / evals | `~/lab/copiloto-bancario/{src,corpus,evals,docs}` |
| Cache de modelos | `~/.cache/huggingface/hub/` |
| Config WSL | `C:\Users\PC PRIDE CALIPSO\.wslconfig` |
