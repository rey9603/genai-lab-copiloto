import requests, time, statistics

URL = "http://localhost:8000/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-14B-Instruct-AWQ"
PROMPT = "Resume en 5 puntos las mejores prácticas de seguridad para un banco al adoptar LLMs en producción."

lat, tps = [], []
print(f"Benchmark: {MODEL}\n{'='*50}")
for i in range(5):
    t0 = time.time()
    r = requests.post(URL, json={
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 400, "temperature": 0.7
    }, timeout=120).json()
    dt = time.time() - t0
    ct = r["usage"]["completion_tokens"]
    lat.append(dt); tps.append(ct / dt)
    print(f"run {i+1}: {dt:5.2f}s | {ct:3d} tokens | {ct/dt:5.1f} tok/s")

print(f"{'='*50}")
print(f"Latencia p50: {statistics.median(lat):.2f}s | Throughput: {statistics.mean(tps):.1f} tok/s promedio")

