#!/usr/bin/env python3
"""
Extrae de Meta Ads el rendimiento DIARIO por anuncio (con su campaña y su
audiencia/conjunto), más la creatividad de cada anuncio: miniatura incrustada
en base64 y enlace para abrirlo. Solo lee.

Guardar a nivel anuncio y por día permite que el dashboard sume en el navegador
cualquier periodo que elija la persona y reconstruya campañas y audiencias sin
volver a llamar a la API.

Uso:  python3 execution/extraer_meta.py [YYYY-MM-DD inicio]
      python3 execution/extraer_meta.py --solo-creatividades   (refresca miniaturas)
Escribe  .tmp/meta.json
"""
import base64, json, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TMP, LOGS = RAIZ / ".tmp", RAIZ / ".tmp" / "logs"
VERSION = "v23.0"
DESDE_POR_DEFECTO = "2026-01-01"

# Qué acción cuenta como resultado. "purchase" ya deduplica píxel + app + tienda.
COMPRA = ["purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase"]
CONVERSACION = ["onsite_conversion.messaging_conversation_started_7d"]
CARRITO = ["add_to_cart", "offsite_conversion.fb_pixel_add_to_cart"]
PAGO = ["initiate_checkout", "offsite_conversion.fb_pixel_initiate_checkout"]
LANDING = ["landing_page_view"]


def leer_env(r):
    v = {}
    for l in r.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, _, val = l.partition("="); v[k.strip()] = val.strip().strip('"').strip("'")
    return v


def pedir(url, token):
    for intento in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode("utf-8", "replace").replace(token, "<TOKEN>")
            if e.code >= 500 or '"code":17' in cuerpo or '"code":4' in cuerpo:
                time.sleep(5 * (intento + 1)); continue   # límite de uso / error temporal
            raise RuntimeError(f"Meta HTTP {e.code}: {cuerpo[:300]}")
        except (urllib.error.URLError, TimeoutError):
            time.sleep(3 * (intento + 1))
    raise RuntimeError("Meta no respondió tras 4 intentos")


def graph(ruta, token, **params):
    params["access_token"] = token
    return f"https://graph.facebook.com/{VERSION}/{ruta}?{urllib.parse.urlencode(params)}"


def todas(url, token):
    filas = []
    while url:
        pag = pedir(url, token)
        filas.extend(pag.get("data", []))
        url = pag.get("paging", {}).get("next")
    return filas


def tramos(desde, hasta, dias):
    d, h = date.fromisoformat(desde), date.fromisoformat(hasta)
    while d <= h:
        fin = min(d + timedelta(days=dias - 1), h)
        yield d.isoformat(), fin.isoformat()
        d = fin + timedelta(days=1)


def insights_rango(cuenta, token, ini, fin):
    url = graph(f"act_{cuenta}/insights", token, level="ad", time_increment=1, limit=100,
                time_range=json.dumps({"since": ini, "until": fin}),
                fields="date_start,campaign_id,adset_id,adset_name,ad_id,ad_name,spend,impressions,"
                       "clicks,inline_link_clicks,actions,action_values")
    try:
        return todas(url, token)
    except RuntimeError as e:
        d0, d1 = date.fromisoformat(ini), date.fromisoformat(fin)
        if "1504018" not in str(e) or d0 == d1:
            raise
        mitad = d0 + (d1 - d0) // 2
        return (insights_rango(cuenta, token, ini, mitad.isoformat())
                + insights_rango(cuenta, token, (mitad + timedelta(days=1)).isoformat(), fin))


def accion(lista, tipos):
    for t in tipos:
        for a in lista or []:
            if a.get("action_type") == t:
                return float(a.get("value", 0))
    return 0.0


def comprimir(crudo):
    """Pasa la miniatura a JPEG de 360 px con `sips` (viene con macOS): las PNG de
    400 px pesan 300 KB+ y el dashboard publicado tiene tope de 16 MB."""
    with tempfile.TemporaryDirectory() as d:
        ent, sal = Path(d) / "in", Path(d) / "out.jpg"
        ent.write_bytes(crudo)
        r = subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "72", "-Z", "360",
                            str(ent), "--out", str(sal)], capture_output=True)
        return sal.read_bytes() if r.returncode == 0 and sal.exists() else None


def creatividades(anuncios, token, cuenta):
    con_img = 0
    for aid, a in anuncios.items():
        try:
            info = pedir(graph(aid, token, fields=(
                "effective_status,preview_shareable_link,"
                "creative.thumbnail_width(400).thumbnail_height(400)"
                "{thumbnail_url,image_url,effective_object_story_id,instagram_permalink_url,video_id}")), token)
        except RuntimeError:
            continue
        cre = info.get("creative") or {}
        a["estado"] = info.get("effective_status")
        a["video"] = bool(cre.get("video_id"))
        historia = cre.get("effective_object_story_id")
        a["enlace"] = (cre.get("instagram_permalink_url")
                       or (f"https://www.facebook.com/{historia}" if historia else None)
                       or info.get("preview_shareable_link")
                       or f"https://adsmanager.facebook.com/adsmanager/manage/ads?act={cuenta}&selected_ad_ids={aid}")
        a["vista_previa"] = info.get("preview_shareable_link")
        a.pop("img", None)
        url_img = cre.get("thumbnail_url") or cre.get("image_url")
        if not url_img:
            continue
        try:
            with urllib.request.urlopen(url_img, timeout=25) as r:
                crudo = r.read()
            jpg = comprimir(crudo) if crudo else None
            if jpg:
                a["img"] = f"data:image/jpeg;base64,{base64.b64encode(jpg).decode()}"
                con_img += 1
        except Exception:
            pass
    return con_img


def solo_creatividades():
    """Refresca miniaturas y enlaces sobre un .tmp/meta.json ya extraído."""
    inicio = time.time()
    env = leer_env(RAIZ / ".env")
    ruta = TMP / "meta.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    con_img = creatividades(datos["anuncios"], env["META_SYSTEM_USER_TOKEN"], datos["cuenta"])
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✓ {con_img} de {len(datos['anuncios'])} anuncios con miniatura → {ruta.relative_to(RAIZ)}")
    registrar("ok", *datos["periodo"], str(ruta.relative_to(RAIZ)), None, inicio,
              {"modo": "solo_creatividades", "miniaturas": con_img})
    return 0


def main():
    inicio = time.time()
    desde = sys.argv[1] if len(sys.argv) > 1 else DESDE_POR_DEFECTO
    hasta = date.today().isoformat()
    env = leer_env(RAIZ / ".env")
    token, cuenta = env["META_SYSTEM_USER_TOKEN"], env["META_AD_ACCOUNT_CUENTISTA"]

    try:
        print(f"Meta · cuenta {cuenta} · {desde} a {hasta}")
        campanas = {c["id"]: c for c in todas(graph(
            f"act_{cuenta}/campaigns", token, fields="id,name,objective,effective_status", limit=200), token)}

        # Diario por anuncio, pedido semana a semana: rangos largos a nivel "ad" con
        # time_increment=1 hacen que Meta corte por tiempo (subcode 1504018). Si una
        # semana también corta, se parte en dos. A nivel "ad" solo acepta límite 100.
        filas = []
        for ini, fin in tramos(desde, hasta, 7):
            filas += insights_rango(cuenta, token, ini, fin)
            print(f"   {ini}: {len(filas):,} filas acumuladas", flush=True)

        anuncios, conjuntos, diario = {}, {}, []
        for f in filas:
            gasto = float(f.get("spend", 0) or 0)
            imp = int(f.get("impressions", 0) or 0)
            if gasto <= 0 and imp == 0:
                continue
            aid = f["ad_id"]
            anuncios.setdefault(aid, {"id": aid, "nombre": f.get("ad_name"),
                                      "conjunto": f["adset_id"], "campana": f["campaign_id"]})
            conjuntos.setdefault(f["adset_id"], {"id": f["adset_id"], "nombre": f.get("adset_name"),
                                                 "campana": f["campaign_id"]})
            acts, vals = f.get("actions"), f.get("action_values")
            # [fecha, anuncio, inversión, impresiones, clics, clics enlace, landing,
            #  carrito, pago iniciado, compras, valor compras, conversaciones]
            diario.append([f["date_start"], aid, round(gasto, 2), imp, int(f.get("clicks", 0) or 0),
                           int(f.get("inline_link_clicks", 0) or 0), int(accion(acts, LANDING)),
                           int(accion(acts, CARRITO)), int(accion(acts, PAGO)),
                           int(accion(acts, COMPRA)), round(accion(vals, COMPRA), 2),
                           int(accion(acts, CONVERSACION))])

        print(f"   {len(anuncios)} anuncios con actividad · pidiendo creatividades…")
        con_img = creatividades(anuncios, token, cuenta)
    except Exception as e:
        registrar("error", desde, hasta, None, str(e), inicio)
        print(f"✗ {e}"); return 1

    TMP.mkdir(parents=True, exist_ok=True)
    destino = TMP / "meta.json"
    destino.write_text(json.dumps({
        "generado": datetime.now().isoformat(timespec="seconds"), "periodo": [desde, hasta],
        "cuenta": cuenta,
        "campanas": {i: {"nombre": c["name"], "objetivo": c.get("objective"), "estado": c.get("effective_status")}
                     for i, c in campanas.items()},
        "conjuntos": conjuntos, "anuncios": anuncios,
        "columnas": ["fecha", "anuncio", "inversion", "impresiones", "clics", "clics_enlace", "landing",
                     "carrito", "pago", "compras", "valor", "conversaciones"],
        "diario": diario,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✓ {len(diario):,} filas · {len(anuncios)} anuncios · {con_img} con miniatura → {destino.relative_to(RAIZ)}")
    registrar("ok", desde, hasta, str(destino.relative_to(RAIZ)), None, inicio,
              {"filas": len(diario), "anuncios": len(anuncios), "miniaturas": con_img})
    return 0


def registrar(estado, desde, hasta, salida, error, inicio, extra=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {"timestamp": datetime.now().isoformat(timespec="seconds"), "script": "execution/extraer_meta.py",
             "inputs": {"periodo": [desde, hasta], **(extra or {})}, "outputs": [salida] if salida else [],
             "status": estado, "error_msg": error, "duration_ms": int((time.time() - inicio) * 1000)}
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(solo_creatividades() if "--solo-creatividades" in sys.argv else main())
