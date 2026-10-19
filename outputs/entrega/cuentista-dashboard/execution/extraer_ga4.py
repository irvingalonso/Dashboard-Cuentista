#!/usr/bin/env python3
"""
Extrae de Google Analytics 4 el comportamiento del sitio de Cuentista, por día:
canal, fuente/medio, dispositivo, hora, página de entrada y el embudo del sitio
(entra → empieza a crear su cuento → carrito → pago → compra). Solo lee.

Solo se piden métricas ADITIVAS (sumables entre días). Rebote, conversión y
duración se calculan después dividiendo sumas, para que el filtro de fechas del
dashboard no promedie promedios. La conversión se mide con compras
(ecommercePurchases / purchase), NUNCA con "eventos clave": en esta propiedad
page_view y session_start están marcados como clave.

Uso:  python3 execution/extraer_ga4.py [YYYY-MM-DD inicio]
Escribe  .tmp/ga4.json
"""
import json, sys, time, urllib.error, urllib.parse, urllib.request
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TMP, LOGS = RAIZ / ".tmp", RAIZ / ".tmp" / "logs"
DESDE_POR_DEFECTO = "2026-01-01"
TOP_FUENTES, TOP_PAGINAS = 20, 20
EMBUDO = ["session_start", "story_config_started", "add_to_cart", "begin_checkout", "purchase"]
# Funnel web del spec: Landing view · Configurador iniciado · Brief completo · Lead · Checkout · Pago.
PASOS_WEB = ["session_start", "story_config_started", "begin_checkout", "purchase"]
PAGINA_BRIEF = "/crea-tu-historia/resumen-y-confirmacion"   # último paso del configurador
PAGINA_LEAD = "/login"                                      # deja sus datos de contacto


def leer_env(r):
    v = {}
    for l in r.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, _, val = l.partition("="); v[k.strip()] = val.strip().strip('"').strip("'")
    return v


def access_token(env):
    d = urllib.parse.urlencode({
        "grant_type": "refresh_token", "refresh_token": env["GOOGLE_ADS_REFRESH_TOKEN"],
        "client_id": env["GOOGLE_ADS_CLIENT_ID"], "client_secret": env["GOOGLE_ADS_CLIENT_SECRET"]}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=d), timeout=30) as r:
        return json.loads(r.read().decode())["access_token"]


def reporte(prop, token, desde, hasta, dims, mets, filtro=None):
    cuerpo = {"dateRanges": [{"startDate": desde, "endDate": hasta}],
              "dimensions": [{"name": d} for d in dims], "metrics": [{"name": m} for m in mets],
              "limit": 250000}
    if filtro:
        cuerpo["dimensionFilter"] = filtro
    req = urllib.request.Request(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport",
        data=json.dumps(cuerpo).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        datos = json.loads(r.read().decode())
    filas = []
    for f in datos.get("rows", []):
        d = [x["value"] for x in f["dimensionValues"]]
        d[0] = f"{d[0][:4]}-{d[0][4:6]}-{d[0][6:]}"   # 20260131 → 2026-01-31
        filas.append(d + [round(float(x["value"]), 2) for x in f["metricValues"]])
    return filas


def recortar(filas, top):
    """Deja las `top` dimensiones con más sesiones y agrupa el resto en "Otros"."""
    total = defaultdict(float)
    for f in filas:
        total[f[1]] += f[2]
    keep = set(sorted(total, key=total.get, reverse=True)[:top])
    acum = defaultdict(lambda: None)
    for f in filas:
        clave = (f[0], f[1] if f[1] in keep else "Otros")
        acum[clave] = [a + b for a, b in zip(acum[clave], f[2:])] if acum[clave] else list(f[2:])
    return [[k[0], k[1]] + [round(x, 2) for x in v] for k, v in acum.items()]


def main():
    inicio = time.time()
    desde = sys.argv[1] if len(sys.argv) > 1 else DESDE_POR_DEFECTO
    hasta = "yesterday"
    env = leer_env(RAIZ / ".env")
    prop = env["GA4_PROPERTY_CUENTISTA"]

    try:
        token = access_token(env)
        print(f"GA4 · propiedad {prop} · desde {desde}")
        base = ["sessions", "engagedSessions", "newUsers", "screenPageViews",
                "userEngagementDuration", "ecommercePurchases", "purchaseRevenue", "addToCarts", "checkouts"]
        canal = reporte(prop, token, desde, hasta, ["date", "sessionDefaultChannelGroup"], base)
        print(f"   canal: {len(canal):,} filas")
        corto = ["sessions", "engagedSessions", "userEngagementDuration", "ecommercePurchases", "purchaseRevenue"]
        fuente = recortar(reporte(prop, token, desde, hasta, ["date", "sessionSourceMedium"], corto), TOP_FUENTES)
        dispositivo = reporte(prop, token, desde, hasta, ["date", "deviceCategory"], corto)
        pagina = recortar(reporte(prop, token, desde, hasta, ["date", "landingPage"], corto), TOP_PAGINAS)
        hora = reporte(prop, token, desde, hasta, ["date", "hour"], ["sessions", "ecommercePurchases"])
        embudo = reporte(prop, token, desde, hasta, ["date", "eventName"], ["eventCount"],
                         {"filter": {"fieldName": "eventName", "inListFilter": {"values": EMBUDO}}})
        # Por campaña (sessionCampaignName = nombre de la campaña de Meta vía UTM),
        # para el funnel web y las ventas atribuidas del tablero semanal.
        y = lambda *fs: {"andGroup": {"expressions": [
            {"filter": {"fieldName": k, "stringFilter": {"value": v}}} for k, v in fs]}}
        camp = reporte(prop, token, desde, hasta, ["date", "sessionCampaignName", "sessionSource"],
                       ["sessions", "ecommercePurchases", "purchaseRevenue"])
        pasos = reporte(prop, token, desde, hasta, ["date", "sessionCampaignName", "eventName"], ["sessions"],
                        {"filter": {"fieldName": "eventName", "inListFilter": {"values": PASOS_WEB}}})
        brief = reporte(prop, token, desde, hasta, ["date", "sessionCampaignName"], ["sessions"],
                        y(("eventName", "story_config_step"), ("pagePath", PAGINA_BRIEF)))
        login = reporte(prop, token, desde, hasta, ["date", "sessionCampaignName"], ["sessions"],
                        y(("eventName", "page_view"), ("pagePath", PAGINA_LEAD)))
        items = reporte(prop, token, desde, hasta, ["date", "sessionCampaignName", "itemCategory"],
                        ["itemsPurchased", "itemRevenue"])
        # Funnel web del spec por canal (pestaña Analytics). Campaña y fuente van para
        # poder sacar las compras que entraron por el link del asesor de WhatsApp.
        dims_c = ["date", "sessionDefaultChannelGroup", "sessionCampaignName", "sessionSource"]
        pasos_canal = reporte(prop, token, desde, hasta, dims_c + ["eventName"], ["sessions"],
                              {"filter": {"fieldName": "eventName", "inListFilter": {"values": PASOS_WEB}}})
        brief_canal = reporte(prop, token, desde, hasta, dims_c, ["sessions"],
                              y(("eventName", "story_config_step"), ("pagePath", PAGINA_BRIEF)))
        # Funnel del formulario: sesiones que vieron cada paso del configurador, por canal.
        form_canal = reporte(prop, token, desde, hasta, dims_c + ["pagePath"], ["sessions"],
                             y(("eventName", "story_config_step")))
        carrito_canal = reporte(prop, token, desde, hasta, dims_c, ["sessions"], y(("eventName", "add_to_cart")))
        print(f"   formulario: {len(form_canal):,} · carrito {len(carrito_canal):,}")
        print(f"   funnel por canal: pasos {len(pasos_canal):,} · brief {len(brief_canal):,}")
        print(f"   por campaña: sesiones {len(camp):,} · pasos {len(pasos):,} · brief {len(brief):,} · "
              f"lead {len(login):,} · items {len(items):,}")
        print(f"   fuente/medio {len(fuente):,} · dispositivo {len(dispositivo):,} · "
              f"página {len(pagina):,} · hora {len(hora):,} · embudo {len(embudo):,}")
    except urllib.error.HTTPError as e:
        msg = f"GA4 HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
        registrar("error", desde, None, msg, inicio); print(f"✗ {msg}"); return 1
    except Exception as e:
        registrar("error", desde, None, str(e), inicio); print(f"✗ {e}"); return 1

    TMP.mkdir(parents=True, exist_ok=True)
    destino = TMP / "ga4.json"
    destino.write_text(json.dumps({
        "generado": datetime.now().isoformat(timespec="seconds"), "desde": desde, "propiedad": prop,
        "columnas": {"canal": ["fecha", "canal"] + base, "corto": ["fecha", "dim"] + corto,
                     "hora": ["fecha", "hora", "sessions", "ecommercePurchases"],
                     "embudo": ["fecha", "evento", "eventCount"]},
        "embudo_pasos": EMBUDO,
        "canal": canal, "fuente": fuente, "dispositivo": dispositivo, "pagina": pagina,
        "hora": hora, "embudo": embudo,
        "campana": {"sesiones": camp, "pasos": pasos, "brief": brief, "lead": login, "items": items,
                    "pagina_brief": PAGINA_BRIEF, "pagina_lead": PAGINA_LEAD},
        "funnel_canal": {"pasos": pasos_canal, "brief": brief_canal, "formulario": form_canal,
                         "carrito": carrito_canal},
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✓ → {destino.relative_to(RAIZ)}")
    registrar("ok", desde, str(destino.relative_to(RAIZ)), None, inicio)
    return 0


def registrar(estado, desde, salida, error, inicio):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {"timestamp": datetime.now().isoformat(timespec="seconds"), "script": "execution/extraer_ga4.py",
             "inputs": {"desde": desde}, "outputs": [salida] if salida else [], "status": estado,
             "error_msg": error, "duration_ms": int((time.time() - inicio) * 1000)}
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
