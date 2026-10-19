#!/usr/bin/env python3
"""
Prueba de conexión con Meta Ads.

Lee las llaves del .env y le pide a Meta los datos básicos de la cuenta
de Cuentista Mx. No modifica nada: solo lee.

Uso:  python3 execution/test_conexion_meta.py
"""
import json, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LOGS = RAIZ / ".tmp" / "logs"
VERSIONES = ["v23.0", "v22.0", "v21.0", "v20.0"]

CUENTAS = [
    ("Cuentista Mx", "META_AD_ACCOUNT_CUENTISTA"),
]


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


def pedir(version, cuenta_id, token, desde, hasta):
    params = urllib.parse.urlencode({
        "fields": "spend,impressions,ctr,purchase_roas",
        "time_range": json.dumps({"since": desde, "until": hasta}),
        "access_token": token,
    })
    url = f"https://graph.facebook.com/{version}/act_{cuenta_id}/insights?{params}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def limpiar(texto, token):
    """Nunca dejar que el token salga en pantalla o en los logs."""
    return texto.replace(token, "<TOKEN OCULTO>") if token else texto


def diagnosticar(token, env):
    """Dice a qué usuario del sistema y a qué app pertenece el token, y qué
    cuentas publicitarias ve. Nunca imprime el token."""
    def get(ruta, **params):
        params["access_token"] = token
        url = f"https://graph.facebook.com/v23.0/{ruta}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    print("\n  Diagnóstico del token:")
    try:
        yo = get("me", fields="id,name")
        print(f"   · Usuario del sistema: {yo.get('name')} (id {yo.get('id')})")
    except Exception as e:
        print(f"   · No pude identificar el usuario: {limpiar(str(e), token)}")
    app_id, secreto = env.get("META_APP_ID", ""), env.get("META_APP_SECRET", "")
    if app_id and secreto:
        try:
            info = get("debug_token", input_token=token).get("data", {})
            print(f"   · App: {info.get('application')} (id {info.get('app_id')})")
            print(f"   · Permisos: {', '.join(info.get('scopes', []))}")
        except Exception as e:
            print(f"   · No pude leer la app del token: {limpiar(str(e), token)}")
    try:
        cuentas = get("me/adaccounts", fields="account_id,name", limit=100).get("data", [])
        print(f"   · Cuentas publicitarias que ve ({len(cuentas)}):")
        for c in cuentas:
            print(f"       - {c.get('name')} ({c.get('account_id')})")
    except Exception as e:
        print(f"   · No pude listar cuentas: {limpiar(str(e), token)}")


def main():
    inicio = time.time()
    env = leer_env(RAIZ / ".env")
    token = env.get("META_SYSTEM_USER_TOKEN", "")

    if not token:
        print("✗ No encontré META_SYSTEM_USER_TOKEN en el .env.")
        print("  Revisa que hayas pegado el token después del signo = y guardado el archivo.")
        return 1

    desde, hasta = "2026-01-01", date.today().isoformat()
    print(f"Probando conexión con Meta Ads  ·  periodo {desde} a {hasta}\n")

    # Detectar qué versión de la API responde
    version_ok, primer_error = None, None
    id_sonda = env.get(CUENTAS[0][1], "")
    for v in VERSIONES:
        try:
            pedir(v, id_sonda, token, desde, hasta)
            version_ok = v
            break
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode("utf-8", "replace")
            if primer_error is None:
                primer_error = limpiar(cuerpo, token)
            if e.code in (400, 404) and "version" in cuerpo.lower():
                continue
            break
        except Exception as e:
            primer_error = limpiar(str(e), token)
            break

    if not version_ok:
        print("✗ Meta rechazó la conexión.\n")
        print(f"  Respuesta de Meta:\n  {primer_error}\n")
        print("  Causas más comunes:")
        print("   · El token se copió incompleto (son muy largos, empiezan con EAA).")
        print("   · Falta el permiso ads_read.")
        print("   · El usuario del sistema no tiene asignada esa cuenta publicitaria.")
        diagnosticar(token, env)
        registrar("error", {"periodo": [desde, hasta]}, [], primer_error, inicio)
        return 1

    print(f"✓ Conexión establecida (API {version_ok})\n")
    print(f"  {'Cuenta':<18} {'Inversión':>14}  {'ROAS':>6}  {'Impresiones':>14}  {'CTR':>6}")
    print(f"  {'-'*18} {'-'*14}  {'-'*6}  {'-'*14}  {'-'*6}")

    resultados, fallos = [], []
    for nombre, clave in CUENTAS:
        cuenta_id = env.get(clave, "")
        if not cuenta_id:
            continue
        try:
            datos = pedir(version_ok, cuenta_id, token, desde, hasta).get("data", [])
            if not datos:
                print(f"  {nombre:<18} {'sin actividad en el periodo':>46}")
                resultados.append({"cuenta": nombre, "estado": "sin datos"})
                continue
            d = datos[0]
            gasto = float(d.get("spend", 0))
            roas = float(d.get("purchase_roas", [{}])[0].get("value", 0)) if d.get("purchase_roas") else 0.0
            impresiones = int(d.get("impressions", 0))
            ctr = float(d.get("ctr", 0))
            print(f"  {nombre:<18} ${gasto:>13,.2f}  {roas:>6.2f}  {impresiones:>14,}  {ctr:>5.2f}%")
            resultados.append({"cuenta": nombre, "inversion": gasto, "roas": roas,
                               "impresiones": impresiones, "ctr": ctr})
        except Exception as e:
            msg = limpiar(str(e), token)
            print(f"  {nombre:<18} ✗ {msg}")
            fallos.append({"cuenta": nombre, "error": msg})

    print()
    if fallos:
        print(f"⚠ {len(fallos)} cuenta(s) fallaron. Suele ser que no se asignaron al usuario del sistema.")
    else:
        print(f"✓ La conexión con Meta quedó lista ({len(CUENTAS)} cuenta).")

    registrar("ok" if not fallos else "error",
              {"periodo": [desde, hasta], "cuentas": len(CUENTAS), "api": version_ok},
              resultados, json.dumps(fallos, ensure_ascii=False) if fallos else None, inicio)
    return 0


def registrar(estado, entradas, salidas, error, inicio):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "script": "execution/test_conexion_meta.py",
        "inputs": entradas,
        "outputs": {"cuentas_leidas": len(salidas)},
        "status": estado,
        "error_msg": error,
        "duration_ms": int((time.time() - inicio) * 1000),
    }
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
