#!/usr/bin/env python3
"""
Prueba de conexión con Supabase (base de datos del sitio de Cuentista).

Lee SUPABASE_URL y SUPABASE_SECRET_KEY del .env, lista las tablas que expone la
API y, de cada una, cuántas filas tiene y qué columnas trae. Solo lee: nunca
escribe ni borra. No imprime valores de las filas (son datos de clientes), solo
nombres de columnas y conteos.

Uso:  python3 execution/test_conexion_supabase.py
"""
import json, sys, time, urllib.error, urllib.request
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LOGS = RAIZ / ".tmp" / "logs"


def leer_env(ruta):
    v = {}
    for l in ruta.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, _, val = l.partition("="); v[k.strip()] = val.strip().strip('"').strip("'")
    return v


def pedir(url, key, metodo="GET", extra=None):
    h = {"apikey": key, "Accept": "application/json"}
    if not key.startswith("sb_"):          # llaves "legacy" (JWT) van también como Bearer
        h["Authorization"] = f"Bearer {key}"
    h.update(extra or {})
    req = urllib.request.Request(url, headers=h, method=metodo)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.headers, r.read()


def registrar(inicio, estado, error=None, extra=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {"timestamp": datetime.now().isoformat(timespec="seconds"),
             "script": "execution/test_conexion_supabase.py", "inputs": extra or {}, "outputs": [],
             "status": estado, "error_msg": error, "duration_ms": int((time.time() - inicio) * 1000)}
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def main():
    inicio = time.time()
    env = leer_env(RAIZ / ".env")
    url, key = env.get("SUPABASE_URL", "").rstrip("/"), env.get("SUPABASE_SECRET_KEY", "")
    if not url or not key:
        print("✗ Faltan SUPABASE_URL o SUPABASE_SECRET_KEY en el .env."); registrar(inicio, "error", "faltan llaves"); return 1
    if key.startswith("sb_publishable"):
        print("✗ Esa es la Publishable key. Hace falta la Secret key (sb_secret_…)."); registrar(inicio, "error", "llave publica"); return 1

    try:
        _, cuerpo = pedir(f"{url}/rest/v1/", key)
        esquema = json.loads(cuerpo)
    except urllib.error.HTTPError as e:
        msg = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:250]}".replace(key, "<LLAVE>")
        pista = {401: "llave inválida o incompleta", 403: "la llave no tiene permiso"}.get(e.code, "")
        print(f"✗ {msg}\n  {pista}"); registrar(inicio, "error", msg); return 1
    except urllib.error.URLError as e:
        print(f"✗ No se pudo llegar a {url}: {e.reason}"); registrar(inicio, "error", str(e.reason)); return 1

    tablas = esquema.get("definitions", {})
    print(f"✓ Conectado a Supabase ({url}) · {len(tablas)} tablas/vistas expuestas\n")
    for nombre in sorted(tablas):
        cols = list((tablas[nombre].get("properties") or {}).keys())
        try:
            h, _ = pedir(f"{url}/rest/v1/{nombre}?select=*&limit=1", key, "HEAD", {"Prefer": "count=exact"})
            total = h.get("Content-Range", "*/?").split("/")[-1]
        except urllib.error.HTTPError as e:
            total = f"sin acceso ({e.code})"
        print(f"  • {nombre:<32} {total:>8} filas  ·  {', '.join(cols[:18])}{' …' if len(cols) > 18 else ''}")
    registrar(inicio, "ok", extra={"tablas": len(tablas)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
