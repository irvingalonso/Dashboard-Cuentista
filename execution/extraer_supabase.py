#!/usr/bin/env python3
"""
Extrae de Supabase (base de datos del sitio de Cuentista) las sesiones de pago
(`checkout_sessions`), que son la base de ventas real del dashboard: monto
cobrado, estado, cupón, físico/digital y la UTM con la que entró el cliente.
Solo lee. No guarda datos personales: ni nombre, ni correo, ni teléfono, ni
dirección; solo fecha, estado, montos, conteos y la campaña de origen.

Uso:  python3 execution/extraer_supabase.py
Escribe  .tmp/supabase.json
"""
import json, sys, time, urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_conexion_supabase import leer_env, pedir

RAIZ = Path(__file__).resolve().parent.parent
TMP, LOGS = RAIZ / ".tmp", RAIZ / ".tmp" / "logs"
MX = ZoneInfo("America/Mexico_City")
CAMPOS = "created_at,status,total_amount,coupon_code,source_url,cart_items"


def a_mx(ts):
    """Supabase guarda en UTC con microsegundos de largo variable (Python 3.9 no los
    parsea con fromisoformat): se toman los segundos y el desfase por separado."""
    base = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
    off = ts[19:].split("+")[-1] if "+" in ts[19:] else "00:00"
    tz = timezone(timedelta(hours=int(off[:2]), minutes=int(off[3:5] or 0)))
    return base.replace(tzinfo=tz).astimezone(MX).strftime("%Y-%m-%d")


def utm(url):
    q = parse_qs(urlparse(url or "").query)
    return (q.get("utm_campaign") or [None])[0], (q.get("utm_source") or [None])[0]


def main():
    inicio = time.time()
    env = leer_env(RAIZ / ".env")
    url, key = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SECRET_KEY"]
    filas, off = [], 0
    try:
        while True:
            _, cuerpo = pedir(f"{url}/rest/v1/checkout_sessions?select={CAMPOS}&order=created_at.asc"
                              f"&limit=1000&offset={off}", key)
            pagina = json.loads(cuerpo)
            filas += pagina
            if len(pagina) < 1000:
                break
            off += 1000
    except urllib.error.HTTPError as e:
        msg = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}".replace(key, "<LLAVE>")
        print(f"✗ {msg}"); registrar("error", None, msg, inicio); return 1

    salida = []
    for f in filas:
        items = f.get("cart_items") if isinstance(f.get("cart_items"), list) else []
        tipos = [(i or {}).get("purchase_type") for i in items if isinstance(i, dict)]
        camp, fuente = utm(f.get("source_url"))
        dia = a_mx(f["created_at"])
        # [fecha MX, estado, monto, cuentos físicos, cuentos digitales, con cupón, utm_campaign, utm_source]
        salida.append([dia, f.get("status"), round(float(f.get("total_amount") or 0), 2),
                       sum(t == "digital_printed" for t in tipos), sum(t == "digital" for t in tipos),
                       int(bool(f.get("coupon_code"))), camp, fuente])

    TMP.mkdir(parents=True, exist_ok=True)
    destino = TMP / "supabase.json"
    destino.write_text(json.dumps({
        "generado": datetime.now().isoformat(timespec="seconds"),
        "columnas": ["fecha", "estado", "monto", "fisicos", "digitales", "cupon", "utm_campaign", "utm_source"],
        "checkouts": salida,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pagadas = [x for x in salida if x[1] in ("completed", "paid")]
    print(f"✓ {len(salida):,} sesiones de pago · {len(pagadas):,} pagadas · "
          f"${sum(x[2] for x in pagadas):,.0f} → {destino.relative_to(RAIZ)}")
    registrar("ok", str(destino.relative_to(RAIZ)), None, inicio, {"checkouts": len(salida), "pagadas": len(pagadas)})
    return 0


def registrar(estado, salida, error, inicio, extra=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {"timestamp": datetime.now().isoformat(timespec="seconds"), "script": "execution/extraer_supabase.py",
             "inputs": extra or {}, "outputs": [salida] if salida else [], "status": estado, "error_msg": error,
             "duration_ms": int((time.time() - inicio) * 1000)}
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
