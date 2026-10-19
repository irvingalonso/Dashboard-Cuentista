#!/usr/bin/env python3
"""
Arma el paquete del proyecto para entregarlo al cliente (Cuentista), listo para
abrirlo con su propio Claude Code.

- Incluye: instrucciones (CLAUDE.md, AGENTS.md, GEMINI.md), directivas, scripts,
  plantilla, parámetros, .env.example, .gitignore, la guía entrega/LEEME.md y el
  último outputs/dashboard.html.
- NUNCA incluye: .env (llaves de Rockin), .tmp/ (datos intermedios y logs).
- Limpia menciones a otros clientes y a cuentas internas de Rockin, y falla si
  después de limpiar queda alguna.

Uso:  python3 execution/empaquetar_entrega.py
Escribe  outputs/cuentista-dashboard.zip
"""
import json, re, shutil, sys, time, zipfile
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OUT, LOGS = RAIZ / "outputs", RAIZ / ".tmp" / "logs"
NOMBRE = "cuentista-dashboard"
INCLUIR = ["CLAUDE.md", "AGENTS.md", "GEMINI.md", ".env.example", ".gitignore", "directives", "execution",
           "outputs/dashboard.html"]
EXCLUIR_EXT = {".pyc"}
EXCLUIR_ARCHIVOS = {".env", "empaquetar_entrega.py"}   # este script es interno de Rockin
# Nada de esto puede salir de Rockin: otros clientes, usuarios del sistema e IDs internos.
PROHIBIDO = re.compile(r"Rec[oó]rcholis|Kataplum|Diniz|\bUPA\b|Rockin IA|Conversions API System User|"
                       r"100057787477946|720910208059161|Lease For|Ever Health|oltex|Eduardo|Johan|6864851833|"
                       r"dashboard-rockin|Recorcholis", re.I)
# Aprendizajes que hablan de otro cliente: se reemplazan por una versión genérica.
APRENDIZAJE_META = ("- **Meta: el token debe ser de un usuario del sistema con la cuenta asignada.** "
                    "El error #200 \"Ad account owner has NOT grant ads_read\" significa que el usuario del sistema "
                    "dueño del token no tiene asignada la cuenta publicitaria (act 4161710000718262). Asignarla en "
                    "Business Manager con \"Ver rendimiento\" y generar el token con `ads_read`. **Por qué importa:** "
                    "que el negocio sea socio no basta; `test_conexion_meta.py` imprime a qué usuario y app pertenece "
                    "el token cuando falla.")
REEMPLAZOS = [
    (re.compile(r"El refresh token de Recórcholis no tiene acceso a Cuentista \(403\); se generó uno nuevo con "
                r"`generar_token_google.py` usando la cuenta que sí la ve \(misma app OAuth, mismo client_id/secret\)\."),
     "Si GA4 responde 403, la cuenta de Google que autorizó el refresh token no ve la propiedad: regenerarlo con "
     "`generar_token_google.py` usando una cuenta que sí tenga acceso."),
    (re.compile(r'La integración "Dashboard Rockin" \(cuenta'), "Una integración privada de Kommo (cuenta"),
    (re.compile(r'llave secreta propia "dashboard-rockin"'), 'llave secreta propia (p. ej. "dashboard")'),
    (re.compile(r'si el token vence o se revoca, basta generar otro en Llaves y alcances'),
     "si el token vence o se revoca, basta generar otro en Llaves y alcances de la integración"),
    (re.compile(r'El token correcto es del robot "Conversions API System User" de Rockin\.'),
     "Asignar la cuenta publicitaria al usuario del sistema dueño del token, con permiso para ver rendimiento."),
    (re.compile(r"`META_APP_ID`/`SECRET` del \.env son de la app [^.]*\."), ""),
]


def limpiar(texto):
    lineas = []
    for l in texto.split("\n"):
        if l.startswith("- **") and "token de Recórcholis NO sirve" in l:
            lineas.append(APRENDIZAJE_META.replace("- **", "- **" + l[4:14] + " — ", 1)
                          if re.match(r"- \*\*\d{4}-\d{2}-\d{2}", l) else APRENDIZAJE_META)
            continue
        lineas.append(l)
    texto = "\n".join(lineas)
    for patron, nuevo in REEMPLAZOS:
        texto = patron.sub(nuevo, texto)
    return texto


def main():
    inicio = time.time()
    destino = OUT / "entrega" / NOMBRE
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    for rel in INCLUIR:
        src = RAIZ / rel
        if not src.exists():
            print(f"⚠ No existe {rel}, se omite"); continue
        archivos = [src] if src.is_file() else [p for p in src.rglob("*") if p.is_file()]
        for f in archivos:
            if f.suffix in EXCLUIR_EXT or "__pycache__" in f.parts or f.name in EXCLUIR_ARCHIVOS:
                continue
            r = f.relative_to(RAIZ); dst = destino / r
            dst.parent.mkdir(parents=True, exist_ok=True)
            if f.suffix in {".md", ".py", ".json", ".example", ""} and f.name != "dashboard.html":
                dst.write_text(limpiar(f.read_text(encoding="utf-8")), encoding="utf-8")
            else:
                shutil.copy2(f, dst)
    shutil.copy2(RAIZ / "entrega" / "LEEME.md", destino / "LEEME.md")

    # Verificación: nada prohibido, ninguna llave.
    problemas = []
    for f in destino.rglob("*"):
        if f.is_file() and f.suffix != ".html":
            t = f.read_text(encoding="utf-8", errors="ignore")
            for m in PROHIBIDO.finditer(t):
                problemas.append(f"{f.relative_to(destino)}: «{m.group(0)}»")
            if re.search(r"(EAA[A-Za-z0-9]{40,}|sb_secret_[A-Za-z0-9_]{10,}|1//0[A-Za-z0-9_-]{20,})", t):
                problemas.append(f"{f.relative_to(destino)}: parece contener una llave")
    if (destino / ".env").exists():
        problemas.append(".env incluido")
    if problemas:
        print("✗ El paquete tiene contenido que no puede salir:\n  " + "\n  ".join(problemas[:20]))
        registrar("error", None, "; ".join(problemas[:5]), inicio); return 1

    zip_ruta = OUT / f"{NOMBRE}.zip"
    with zipfile.ZipFile(zip_ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(destino.rglob("*")):
            if f.is_file():
                z.write(f, Path(NOMBRE) / f.relative_to(destino))
    n = sum(1 for f in destino.rglob("*") if f.is_file())
    print(f"✓ {n} archivos · sin llaves ni menciones a otros clientes → {zip_ruta.relative_to(RAIZ)} "
          f"({zip_ruta.stat().st_size / 1e6:.1f} MB)")
    registrar("ok", str(zip_ruta.relative_to(RAIZ)), None, inicio, {"archivos": n})
    return 0


def registrar(estado, salida, error, inicio, extra=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {"timestamp": datetime.now().isoformat(timespec="seconds"), "script": "execution/empaquetar_entrega.py",
             "inputs": extra or {}, "outputs": [salida] if salida else [], "status": estado, "error_msg": error,
             "duration_ms": int((time.time() - inicio) * 1000)}
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
