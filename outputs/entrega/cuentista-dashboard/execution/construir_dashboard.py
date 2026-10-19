#!/usr/bin/env python3
"""
Construye el dashboard HTML de Cuentista a partir de los datos ya extraídos.

Lee   .tmp/kommo.json, .tmp/meta.json, .tmp/meta_semanal.json, .tmp/ga4.json
      execution/parametros_tablero.json
      execution/plantilla_dashboard.html
Escribe  outputs/dashboard.html

Toda la lógica de filtros y hallazgos vive en la plantilla (JS en el navegador);
aquí solo se compactan los datos y se incrustan. El HTML es un entregable
reproducible: no se edita a mano (regla dura #5).

Uso:  python3 execution/construir_dashboard.py
"""
import json, sys, time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from armar_semanal import armar

RAIZ = Path(__file__).resolve().parent.parent
TMP, LOGS, OUT = RAIZ / ".tmp", RAIZ / ".tmp" / "logs", RAIZ / "outputs"
MX = ZoneInfo("America/Mexico_City")
ORDEN_FASES = ["e", "s", "t", "d", "r"]   # entrada, salida, toques, días con toque, respuestas
UMBRAL_MASIVO = 50   # más de esto entrando a cierre el mismo día = movimiento en bloque


def dia_mx(ts):
    return datetime.fromtimestamp(ts, MX).strftime("%Y-%m-%d") if ts else None


def compactar_kommo(k, sub):
    leads = []
    for l in k["leads"]:
        fs = {f: [v[c] if v[c] is not None else 0 for c in ORDEN_FASES] for f, v in l["fs"].items()}
        leads.append({
            "id": l["id"], "c": l["c"], "d": dia_mx(l["c"]), "st": l["st"],
            "mig": l.get("mig", False), "lsa": l.get("lsa", False),
            "pg": l["pg"] or 0, "pgd": dia_mx(l["pg"]), "m": l["m"] or 0, "f": l["f"] or "",
            "lr": l["lr"] or "", "pr": l["pr"],
            "pd": dia_mx(l["fs"]["perdido"]["e"]) if "perdido" in l["fs"] else None,
            "fs": fs,
            # brief: tm = tema definido · bc = brief completo (nombre, edad, rasgos, tema, escenario)
            "tm": bool((l.get("br") or {}).get("tema")),
            "bc": all((l.get("br") or {}).get(x) for x in ("nombre", "edad", "rasgos", "tema", "escenario")),
        })
    # Movimientos en bloque a cierre (p. ej. 236 leads de Leadsales el 2026-09-04) son
    # migración de pedidos viejos, no ventas de ese día: se quitan de ventas.
    por_dia = {}
    for x in leads:
        if x["pgd"]:
            por_dia[x["pgd"]] = por_dia.get(x["pgd"], 0) + 1
    for x in leads:
        if x["pgd"] and por_dia[x["pgd"]] >= UMBRAL_MASIVO:
            x.update(pg=0, pgd=None, m=0, pm=True)
    return {
        "sub": sub, "umbral_masivo": UMBRAL_MASIVO, "ahora": int(datetime.fromisoformat(k["generado"]).timestamp()),
        "etapas": k["etapas"], "mapeo": k["fases_mapeo"], "cierre": k["etapas_cierre"],
        "primer_lead": min(x["d"] for x in leads) if leads else None, "leads": leads,
    }


def funnel_web_canal(g, params):
    """Funnel web del spec por día y canal: [fecha, canal, entró por WhatsApp (0/1), paso, sesiones].
    Pasos: 0 landing · 1 configurador · 2 brief · 3 lead (sin evento) · 4 checkout · 5 pago."""
    wa = {tuple(x) for x in params["whatsapp_en_web"]}
    paso = {"session_start": 0, "story_config_started": 1, "begin_checkout": 4, "purchase": 5}
    acum = {}
    fc = g["funnel_canal"]
    filas = [(f, ch, cn, src, paso.get(ev), s) for f, ch, cn, src, ev, s in fc["pasos"]]
    filas += [(f, ch, cn, src, 2, s) for f, ch, cn, src, s in fc["brief"]]
    for f, ch, cn, src, p, s in filas:
        if p is None:
            continue
        k = (f, ch, int((cn, src) in wa), p)
        acum[k] = acum.get(k, 0) + s
    return [[*k, round(v)] for k, v in acum.items()]


PASOS_FORM = ["Inicio", "Paquete", "Aventura", "Protagonista", "Personalización", "Resumen", "Checkout", "Compra"]
PAGINA_FORM = {"elige-tu-paquete": 1, "la-aventura": 2, "el-protagonista": 3,
               "personalizacion-avanzada": 4, "resumen-y-confirmacion": 5}


def funnel_formulario(g, params):
    """Funnel del formulario (configurador) por día y canal: [fecha, canal, entró por WhatsApp, paso, sesiones].
    Pasos 0–7 = PASOS_FORM; 8 = sesiones iniciadas y 9 = carritos (KPIs, no escalones)."""
    wa = {tuple(x) for x in params["whatsapp_en_web"]}
    fc = g["funnel_canal"]
    ev = {"story_config_started": 0, "begin_checkout": 6, "purchase": 7, "session_start": 8}
    filas = [(f, ch, cn, src, ev.get(e), s) for f, ch, cn, src, e, s in fc["pasos"]]
    filas += [(f, ch, cn, src, PAGINA_FORM.get(pp.rstrip("/").split("/")[-1]), s) for f, ch, cn, src, pp, s in fc["formulario"]]
    filas += [(f, ch, cn, src, 9, s) for f, ch, cn, src, s in fc["carrito"]]
    acum = {}
    for f, ch, cn, src, p, s in filas:
        if p is None:
            continue
        k = (f, ch, int((cn, src) in wa), p)
        acum[k] = acum.get(k, 0) + s
    return [[*k, round(v)] for k, v in acum.items()]


def main():
    inicio = time.time()
    faltan = [n for n in ("kommo.json", "meta.json", "meta_semanal.json", "ga4.json") if not (TMP / n).exists()]
    if faltan:
        print(f"✗ Faltan extracciones en .tmp/: {', '.join(faltan)}. Corre primero los extractores.")
        return 1
    k = json.loads((TMP / "kommo.json").read_text(encoding="utf-8"))
    m = json.loads((TMP / "meta.json").read_text(encoding="utf-8"))
    g = json.loads((TMP / "ga4.json").read_text(encoding="utf-8"))
    ms = json.loads((TMP / "meta_semanal.json").read_text(encoding="utf-8"))
    sb_ruta = TMP / "supabase.json"
    sb = json.loads(sb_ruta.read_text(encoding="utf-8")) if sb_ruta.exists() else None
    params = json.loads((RAIZ / "execution" / "parametros_tablero.json").read_text(encoding="utf-8"))
    env = dict(l.split("=", 1) for l in (RAIZ / ".env").read_text(encoding="utf-8").splitlines()
               if "=" in l and not l.lstrip().startswith("#"))
    sub = env.get("KOMMO_SUBDOMAIN", "").strip()

    datos = {
        "generado": datetime.now(MX).strftime("%Y-%m-%d %H:%M"),
        "hoy": datetime.now(MX).strftime("%Y-%m-%d"),
        "inicio": min(m["periodo"][0], g["desde"]),
        "semanal": armar(k, ms, g, params),
        # Base de ventas real (Supabase · checkout_sessions): [fecha, estado, monto, físicos, digitales, cupón, utm_campaign, utm_source]
        "supabase": sb["checkouts"] if sb else [],
        "kommo": compactar_kommo(k, sub),
        "meta": {"cuenta": m["cuenta"], "campanas": m["campanas"], "conjuntos": m["conjuntos"],
                 "anuncios": m["anuncios"], "diario": m["diario"]},
        "ga4": {"propiedad": g["propiedad"], "pasos": g["embudo_pasos"], "canal": g["canal"],
                "fuente": g["fuente"], "dispositivo": g["dispositivo"], "pagina": g["pagina"],
                "hora": g["hora"], "embudo": g["embudo"], "fw": funnel_web_canal(g, params),
                "ff": funnel_formulario(g, params), "pasos_form": PASOS_FORM},
    }
    # Frescura: hasta qué fecha llega cada fuente. Si una quedó atrás (p. ej. se corrió
    # solo el extractor semanal de Meta), el dashboard mostraría días en cero que no lo son.
    hoy = date.fromisoformat(datos["hoy"])
    frescura = {
        "Meta diario": max((r[0] for r in m["diario"]), default=None),
        "Meta semanal": ms["generado"][:10],
        "GA4": max((r[0] for r in g["canal"]), default=None),
        "Kommo": k["generado"][:10],
        "Supabase": sb["generado"][:10] if sb else None,
    }
    datos["frescura"] = frescura
    atrasadas = [f"{n} (hasta {d})" for n, d in frescura.items() if not d or (hoy - date.fromisoformat(d)).days > 2]
    if atrasadas:
        print("⚠ Fuentes atrasadas más de 2 días: " + ", ".join(atrasadas) + ". Corre sus extractores antes de publicar.")
    js = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    plantilla = (RAIZ / "execution" / "plantilla_dashboard.html").read_text(encoding="utf-8")
    if "/*__DATA__*/null" not in plantilla:
        print("✗ La plantilla no tiene el marcador /*__DATA__*/null"); return 1
    html = plantilla.replace("/*__DATA__*/null", js)

    OUT.mkdir(parents=True, exist_ok=True)
    destino = OUT / "dashboard.html"
    destino.write_text(html, encoding="utf-8")
    mb = destino.stat().st_size / 1e6
    print(f"✓ {destino.relative_to(RAIZ)} · {mb:.1f} MB · {len(datos['kommo']['leads']):,} leads · "
          f"{len(m['diario']):,} filas Meta · {len(m['anuncios'])} anuncios")
    if mb > 15:
        print("⚠ Pasa de 15 MB: el límite de publicación es 16 MB.")

    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": datetime.now().isoformat(timespec="seconds"),
                            "script": "execution/construir_dashboard.py",
                            "inputs": {"kommo": k["generado"], "meta": m["generado"], "ga4": g["generado"]},
                            "outputs": [str(destino.relative_to(RAIZ))], "status": "ok", "error_msg": None,
                            "duration_ms": int((time.time() - inicio) * 1000)}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
