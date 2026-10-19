#!/usr/bin/env python3
"""
Genera el refresh token de Google Ads (la última pieza de la conexión).

Abre tu navegador, te pide autorizar con tu cuenta de Google, y guarda el
permiso en el .env. Solo hay que correrlo una vez: el refresh token no caduca
(siempre que la app OAuth esté marcada como "Interno" o publicada en producción).

Uso:  python3 execution/generar_token_google.py
"""
import http.server, json, secrets, socketserver, sys, threading, time
import urllib.error, urllib.parse, urllib.request, webbrowser
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LOGS = RAIZ / ".tmp" / "logs"
ALCANCE = " ".join([
    "https://www.googleapis.com/auth/adwords",            # Google Ads
    "https://www.googleapis.com/auth/analytics.readonly",  # Google Analytics 4
])
AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
CANJEAR = "https://oauth2.googleapis.com/token"

recibido = {}


def leer_env(ruta):
    v = {}
    if ruta.exists():
        for l in ruta.read_text(encoding="utf-8").splitlines():
            l = l.strip()
            if l and not l.startswith("#") and "=" in l:
                k, _, val = l.partition("=")
                v[k.strip()] = val.strip().strip('"').strip("'")
    return v


def guardar_en_env(ruta, clave, valor):
    lineas = ruta.read_text(encoding="utf-8").splitlines(keepends=True)
    salida, puesto = [], False
    for l in lineas:
        if l.startswith(f"{clave}="):
            salida.append(f"{clave}={valor}\n"); puesto = True
        else:
            salida.append(l)
    if not puesto:
        salida.append(f"{clave}={valor}\n")
    ruta.write_text("".join(salida), encoding="utf-8")


class Manejador(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        recibido.update({k: v[0] for k, v in q.items()})
        ok = "code" in recibido
        cuerpo = (
            "<html><meta charset='utf-8'><body style='font-family:system-ui;"
            "text-align:center;padding:60px'>"
            + ("<h2>✓ Listo</h2><p>Ya puedes cerrar esta pestaña y volver a la terminal.</p>"
               if ok else
               f"<h2>✗ Algo falló</h2><p>{recibido.get('error','sin detalle')}</p>")
            + "</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(cuerpo.encode("utf-8"))

    def log_message(self, *a):
        pass  # sin ruido en la terminal


def registrar(estado, error, inicio):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "script": "execution/generar_token_google.py",
        "inputs": {"scope": ALCANCE},
        "outputs": {"refresh_token": "escrito en .env" if estado == "ok" else None},
        "status": estado,
        "error_msg": error,
        "duration_ms": int((time.time() - inicio) * 1000),
    }
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def main():
    inicio = time.time()
    env_path = RAIZ / ".env"
    env = leer_env(env_path)
    cid, secreto = env.get("GOOGLE_ADS_CLIENT_ID", ""), env.get("GOOGLE_ADS_CLIENT_SECRET", "")

    if not cid or not secreto:
        print("✗ Faltan GOOGLE_ADS_CLIENT_ID o GOOGLE_ADS_CLIENT_SECRET en el .env.")
        return 1

    with socketserver.TCPServer(("127.0.0.1", 0), Manejador) as servidor:
        puerto = servidor.server_address[1]
        redirect = f"http://localhost:{puerto}"
        estado = secrets.token_urlsafe(16)
        url = AUTORIZAR + "?" + urllib.parse.urlencode({
            "client_id": cid, "redirect_uri": redirect, "response_type": "code",
            "scope": ALCANCE, "access_type": "offline", "prompt": "consent", "state": estado,
        })

        print("Se va a abrir tu navegador para que autorices el acceso.\n")
        print("  1. Elige la cuenta de Google que tiene acceso a Google Analytics de Cuentista")
        print("  2. Si sale un aviso de 'Google no verificó esta app' → Configuración avanzada → Continuar")
        print("  3. Dale Permitir\n")
        print(f"Si no se abre solo, pega esta dirección en el navegador:\n{url}\n")
        print("Esperando autorización...")

        threading.Thread(target=servidor.handle_request, daemon=True).start()
        webbrowser.open(url)

        limite = time.time() + 300
        while "code" not in recibido and "error" not in recibido and time.time() < limite:
            time.sleep(0.4)

    if "error" in recibido:
        msg = recibido["error"]
        print(f"\n✗ Google rechazó la autorización: {msg}")
        if "access_denied" in msg or "blocked" in msg.lower():
            print("  Suele ser que la app OAuth siguió en modo 'Prueba' con usuarios externos.")
            print("  Ve a Google Auth Platform → Público → 'Marcar como interno'.")
        registrar("error", msg, inicio); return 1

    if "code" not in recibido:
        print("\n✗ Se acabó el tiempo de espera sin recibir autorización.")
        registrar("error", "timeout", inicio); return 1

    if recibido.get("state") != estado:
        print("\n✗ La respuesta no coincide con la petición. Vuelve a intentarlo.")
        registrar("error", "state mismatch", inicio); return 1

    datos = urllib.parse.urlencode({
        "code": recibido["code"], "client_id": cid, "client_secret": secreto,
        "redirect_uri": redirect, "grant_type": "authorization_code",
    }).encode()

    try:
        with urllib.request.urlopen(urllib.request.Request(CANJEAR, data=datos), timeout=30) as r:
            tok = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")
        print(f"\n✗ Error al canjear el código:\n  {msg}")
        registrar("error", msg, inicio); return 1

    refresh = tok.get("refresh_token")
    if not refresh:
        print("\n✗ Google no devolvió refresh_token.")
        print("  Suele pasar si ya habías autorizado antes. Revoca el acceso en")
        print("  myaccount.google.com/permissions y vuelve a correr este script.")
        registrar("error", "sin refresh_token", inicio); return 1

    guardar_en_env(env_path, "GOOGLE_ADS_REFRESH_TOKEN", refresh)
    print(f"\n✓ Refresh token generado y guardado en .env ({len(refresh)} caracteres)")
    print("  No se muestra en pantalla por seguridad.")
    registrar("ok", None, inicio)
    return 0


if __name__ == "__main__":
    sys.exit(main())
