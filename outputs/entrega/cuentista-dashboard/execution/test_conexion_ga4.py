#!/usr/bin/env python3
"""
Prueba de conexión con Google Analytics 4.

Usa las credenciales OAuth de Google del .env (las mismas de Google Ads, con
el permiso analytics.readonly) y pide a GA4 las sesiones, usuarios y compras
de los últimos 30 días de la propiedad de Cuentista. No modifica nada: solo lee.

Uso:  python3 execution/test_conexion_ga4.py
"""
import json, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LOGS = RAIZ / ".tmp" / "logs"
NECESARIAS = ["GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
              "GOOGLE_ADS_REFRESH_TOKEN", "GA4_PROPERTY_CUENTISTA"]


def leer_env(ruta):
    """Lee un .env simple (CLAVE=valor) sin dependencias externas."""
    valores = {}
    if not ruta.exists():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def access_token(env):
    datos = urllib.parse.urlencode({
        "grant_type": "refresh_token", "refresh_token": env["GOOGLE_ADS_REFRESH_TOKEN"],
        "client_id": env["GOOGLE_ADS_CLIENT_ID"], "client_secret": env["GOOGLE_ADS_CLIENT_SECRET"]}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=datos)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())["access_token"]


def reporte(prop, token):
    cuerpo = json.dumps({
        "dateRanges": [{"startDate": "30daysAgo", "endDate": "yesterday"}],
        "metrics": [{"name": m} for m in ("sessions", "totalUsers", "ecommercePurchases", "purchaseRevenue")],
    }).encode()
    req = urllib.request.Request(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport",
        data=cuerpo, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def diagnosticar(token):
    """Lista las propiedades de GA4 que ve el token, para comparar el ID."""
    print("\n  Diagnóstico: propiedades de GA4 que ve esta cuenta de Google:")
    try:
        req = urllib.request.Request(
            "https://analyticsadmin.googleapis.com/v1beta/accountSummaries?pageSize=200",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            cuentas = json.loads(r.read().decode()).get("accountSummaries", [])
    except urllib.error.HTTPError as e:
        print(f"   · No pude listarlas (HTTP {e.code}): {e.read().decode('utf-8', 'replace')[:200]}")
        return
    if not cuentas:
        print("   · Ninguna. Esta cuenta de Google no tiene acceso a ninguna propiedad de GA4.")
    for c in cuentas:
        print(f"   · Cuenta: {c.get('displayName')} ({c.get('account', '').split('/')[-1]})")
        for p in c.get("propertySummaries", []):
            print(f"       - {p.get('displayName')}  →  ID {p.get('property', '').split('/')[-1]}")


def registrar(inicio, status, error_msg=None, prop=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "script": "test_conexion_ga4.py",
        "inputs": {"propiedad": prop, "periodo": "últimos 30 días"},
        "outputs": [],
        "status": status,
        "error_msg": error_msg,
        "duration_ms": int((time.time() - inicio) * 1000),
    }
    with open(LOGS / f"{date.today().isoformat()}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def main():
    inicio = time.time()
    env = leer_env(RAIZ / ".env")
    prop = env.get("GA4_PROPERTY_CUENTISTA", "")

    faltan = [k for k in NECESARIAS if not env.get(k)]
    if faltan:
        msg = f"Faltan en .env: {', '.join(faltan)}"
        print(f"✗ {msg}")
        registrar(inicio, "error", msg, prop)
        return 1

    try:
        token = access_token(env)
    except urllib.error.HTTPError as e:
        msg = f"Google rechazó las credenciales (HTTP {e.code}): {e.read().decode('utf-8', 'replace')[:200]}"
        print(f"✗ {msg}")
        print("  Suele ser: client_id/secret copiados incompletos, o el refresh token caducó o fue revocado.")
        registrar(inicio, "error", msg, prop)
        return 1

    try:
        datos = reporte(prop, token)
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")[:300]
        pista = {
            403: "la cuenta de Google que autorizó el refresh token no tiene acceso a esta propiedad, "
                 "o el token no incluye el permiso analytics.readonly",
            400: "el Property ID es incorrecto (debe ser el numérico, no el G-XXXXXXX)",
            404: "no existe una propiedad con ese ID",
        }.get(e.code, "")
        msg = f"HTTP {e.code}: {pista} | {cuerpo}"
        print(f"✗ {msg}")
        diagnosticar(token)
        registrar(inicio, "error", msg, prop)
        return 1

    fila = (datos.get("rows") or [{}])[0].get("metricValues", [])
    valores = [float(m.get("value", 0)) for m in fila] or [0, 0, 0, 0]
    sesiones, usuarios, compras, ingreso = valores
    print(f"✓ Conectado a GA4 (propiedad {prop}) · últimos 30 días\n")
    print(f"  Sesiones:  {int(sesiones):>12,}")
    print(f"  Usuarios:  {int(usuarios):>12,}")
    print(f"  Compras:   {int(compras):>12,}")
    print(f"  Ingreso:   ${ingreso:>11,.2f}")
    registrar(inicio, "ok", prop=prop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
