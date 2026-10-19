#!/usr/bin/env python3
"""
Arma los bloques semanales del tablero del spec (lunes a domingo) a partir de
las extracciones de Kommo, Meta semanal y GA4. Lo usa construir_dashboard.py.

Aquí solo se suman datos crudos por semana, campaña y destino. Las métricas
derivadas (CAC, margen, ROAS piso/techo, cobertura, pérdida en puntos) se
calculan en el navegador, porque dependen de qué campañas elija la persona.

Reglas del spec que se aplican aquí:
- El canal se asigna por punto de entrada: una compra web que llegó por el link
  que manda el asesor de WhatsApp es venta de WhatsApp, no de Web.
- El total y el desglose son números distintos: lo que no se liga a una
  campaña queda como "sin origen", nunca se reparte.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MX = ZoneInfo("America/Mexico_City")
PASOS_WA = ["Conversación iniciada", "Apertura del asesor", "Tema definido", "Brief completo",
            "Formato elegido", "Cierre solicitado", "Pago confirmado"]
PASOS_WEB = ["Landing view", "Configurador iniciado", "Brief completo", "Lead (datos)",
             "Checkout iniciado", "Pago confirmado"]
DESTINO = {"OUTCOME_LEADS": "wa", "OUTCOME_ENGAGEMENT": "wa", "OUTCOME_SALES": "web", "OUTCOME_TRAFFIC": "web"}


def lunes(d):
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return (d - timedelta(days=d.weekday())).isoformat()


def lunes_ts(ts):
    return lunes(datetime.fromtimestamp(ts, MX).date())


def armar(kommo, meta_sem, ga4, params):
    semanas = meta_sem["semanas"]
    camp = {i: {"nombre": c["nombre"], "destino": DESTINO.get(c["objetivo"], "web"), "estado": c["estado"]}
            for i, c in meta_sem["campanas"].items()}
    por_nombre = {c["nombre"]: i for i, c in camp.items()}

    def meta(filas):
        o = defaultdict(dict)
        for r in filas:
            o[r["id"]][r["semana"]] = {k: r[k] for k in ("gasto", "imp", "alcance", "frec", "clics_enlace",
                                                         "lpv", "conversaciones", "compras", "valor")}
        return o
    mc, ma = meta(meta_sem["por_campana"]), meta(meta_sem["por_conjunto"])
    activas = {i for i in mc}

    # ── GA4 por campaña ────────────────────────────────────────────────
    wa_fuentes = {tuple(x) for x in params["whatsapp_en_web"]}
    wa_campanas_ga = {c for c, _ in wa_fuentes}
    cero = lambda: {"landing": 0, "config": 0, "brief": 0, "lead": 0, "checkout": 0, "pago": 0,
                    "fis": 0, "dig": 0}
    web = defaultdict(lambda: defaultdict(cero))
    web_otros = defaultdict(lambda: {"pago": 0, "fis": 0, "dig": 0})
    wa_web = defaultdict(int)
    g = ga4["campana"]
    for f, cn, fuente, ses, compras, _ing in g["sesiones"]:
        s = lunes(f)
        if (cn, fuente) in wa_fuentes:
            wa_web[s] += compras
        elif cn in por_nombre:
            web[por_nombre[cn]][s]["landing"] += ses
            web[por_nombre[cn]][s]["pago"] += compras
        else:
            web_otros[s]["pago"] += compras
    clave = {"story_config_started": "config", "begin_checkout": "checkout"}
    for f, cn, ev, ses in g["pasos"]:
        if cn in por_nombre and ev in clave:
            web[por_nombre[cn]][lunes(f)][clave[ev]] += ses
    for nombre_lista, k in (("brief", "brief"), ("lead", "lead")):
        for f, cn, ses in g[nombre_lista]:
            if cn in por_nombre:
                web[por_nombre[cn]][lunes(f)][k] += ses
    for f, cn, cat, n, _rev in g["items"]:
        k = "fis" if cat.lower().startswith("f") else "dig" if cat.lower().startswith("d") else None
        if not k or cn in wa_campanas_ga:
            continue
        (web[por_nombre[cn]][lunes(f)] if cn in por_nombre else web_otros[lunes(f)])[k] += n

    # ── Kommo: ventas por semana de pago y funnel WA por semana de entrada ──
    leads = kommo["leads"]
    ventas_dia = defaultdict(int)
    for l in leads:
        if l["pg"] and not l.get("mig"):
            ventas_dia[datetime.fromtimestamp(l["pg"], MX).date()] += 1
    masivo = {d for d, n in ventas_dia.items() if n >= 50}
    wa_ventas = defaultdict(lambda: {"n": 0, "fis": 0, "dig": 0})
    wa_funnel = defaultdict(lambda: [0] * len(PASOS_WA))
    cierre = set(kommo["etapas_cierre"])
    for l in leads:
        if l.get("mig"):
            continue
        pago = l["pg"] and datetime.fromtimestamp(l["pg"], MX).date() not in masivo
        if pago:
            v = wa_ventas[lunes_ts(l["pg"])]
            v["n"] += 1
            if l["f"] == "Físico": v["fis"] += 1
            elif l["f"] == "Digital": v["dig"] += 1
        if l.get("lsa"):
            continue   # Leadsales: flujo de migración, fuera del funnel (ver directiva)
        fs, br = l["fs"], l.get("br") or {}
        avanzado = bool(fs.get("finalizado") or fs.get("pendiente_pago") or pago)
        pendiente = bool(fs.get("pendiente_pago") or pago)
        pasos = [True, bool(l.get("po")), br.get("tema") or avanzado,
                 all(br.get(k) for k in ("nombre", "edad", "rasgos", "tema", "escenario")) or avanzado,
                 br.get("formato") or pendiente, pendiente, bool(pago)]
        # Escalera: quien llegó a un escalón pasó por todos los anteriores.
        for i in range(len(pasos) - 2, -1, -1):
            pasos[i] = pasos[i] or pasos[i + 1]
        fila = wa_funnel[lunes_ts(l["c"])]
        for i, ok in enumerate(pasos):
            fila[i] += int(bool(ok))

    primer = min((l["c"] for l in leads), default=None)
    return {
        "params": params, "semanas": semanas, "en_curso": meta_sem["semana_en_curso"],
        "kommo_desde": lunes_ts(primer) if primer else None,
        "pasos_wa": PASOS_WA, "pasos_web": PASOS_WEB,
        "campanas": {i: c for i, c in camp.items() if i in activas},
        "conjuntos": meta_sem["conjuntos"], "mc": mc, "ma": ma,
        "web": {i: dict(v) for i, v in web.items()}, "web_otros": dict(web_otros), "wa_web": dict(wa_web),
        "wa_ventas": dict(wa_ventas), "wa_funnel": dict(wa_funnel),
        "ga4_campana_rota": sum(r[3] for r in g["sesiones"] if "{{" in r[1]),
    }
