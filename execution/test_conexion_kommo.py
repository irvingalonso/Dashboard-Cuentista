#!/usr/bin/env python3
"""
Prueba de conexión con Kommo (CRM).

Lee KOMMO_SUBDOMAIN y KOMMO_LONG_LIVED_TOKEN del .env y le pide a Kommo los
datos básicos de la cuenta y la lista de embudos (pipelines) con sus etapas.
No modifica nada: solo lee.

Uso:  python3 execution/test_conexion_kommo.py
"""
import json, sys, time, urllib.error, urllib.request
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LOGS = RAIZ / ".tmp" / "logs"


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


def pedir(subdominio, token, ruta):
    url = f"https://{subdominio}.kommo.com/api/v4/{ruta}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        cuerpo = r.read().decode("utf-8")
        return json.loads(cuerpo) if cuerpo else {}


def registrar(inicio, status, error_msg=None, subdominio=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "script": "test_conexion_kommo.py",
        "inputs": {"subdominio": subdominio},
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
    subdominio = env.get("KOMMO_SUBDOMAIN", "").replace(".kommo.com", "").replace("https://", "").strip("/")
    token = env.get("KOMMO_LONG_LIVED_TOKEN", "")

    faltan = [k for k, v in (("KOMMO_SUBDOMAIN", subdominio), ("KOMMO_LONG_LIVED_TOKEN", token)) if not v]
    if faltan:
        msg = f"Faltan en .env: {', '.join(faltan)}"
        print(f"✗ {msg}")
        registrar(inicio, "error", msg, subdominio)
        sys.exit(1)

    try:
        cuenta = pedir(subdominio, token, "account")
        print(f"✓ Conectado a Kommo: {cuenta.get('name')} (id {cuenta.get('id')}, {subdominio}.kommo.com)")

        embudos = pedir(subdominio, token, "leads/pipelines").get("_embedded", {}).get("pipelines", [])
        print(f"\nEmbudos encontrados: {len(embudos)}")
        for p in embudos:
            etapas = p.get("_embedded", {}).get("statuses", [])
            print(f"  • {p['name']} (id {p['id']}) — {len(etapas)} etapas")
            for e in sorted(etapas, key=lambda x: x.get("sort", 0)):
                print(f"      - {e['name']} (id {e['id']})")
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="replace")[:300]
        pista = {
            401: "token inválido, vencido o revocado — genera uno nuevo en Llaves y alcances",
            403: "la integración no tiene alcance suficiente — revisa los permisos en Editar",
            404: "subdominio incorrecto o endpoint inexistente",
        }.get(e.code, "")
        msg = f"HTTP {e.code}: {pista} | {detalle}"
        print(f"✗ {msg}")
        registrar(inicio, "error", msg, subdominio)
        sys.exit(1)
    except urllib.error.URLError as e:
        msg = f"No se pudo llegar a {subdominio}.kommo.com: {e.reason}"
        print(f"✗ {msg}")
        registrar(inicio, "error", msg, subdominio)
        sys.exit(1)

    registrar(inicio, "ok", subdominio=subdominio)


if __name__ == "__main__":
    main()
