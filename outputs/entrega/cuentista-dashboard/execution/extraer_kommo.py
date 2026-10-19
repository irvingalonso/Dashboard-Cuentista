#!/usr/bin/env python3
"""
Extrae de Kommo los leads, su historial de etapas y sus mensajes, y los
resume por lead contra el funnel operativo nuevo (Miro). Solo lee.

Por cada lead calcula, fase por fase: cuándo entró, cuándo salió, cuántos
toques (mensajes nuestros) recibió, en cuántos días distintos, y si el cliente
respondió. Con eso el dashboard mide las cadencias propuestas sin cargar
decenas de miles de mensajes en el navegador.

Uso:  python3 execution/extraer_kommo.py [YYYY-MM-DD inicio]
Escribe  .tmp/kommo.json
"""
import json, sys, time, urllib.error, urllib.request
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TMP, LOGS = RAIZ / ".tmp", RAIZ / ".tmp" / "logs"
DESDE_POR_DEFECTO = "2026-01-01"
PIPELINE = 14306191
PAGO_REALIZADO, GANADO, PERDIDO = 110485059, 142, 143
PRECIO = {"Digital": 149, "Físico": 449}   # MXN; el price de Kommo viene en 0
# Campos del brief en Kommo → llave corta. Brief completo = los cinco primeros.
BRIEF = {"nombre": "Nombre del peque", "edad": "Edad del peque", "rasgos": "Características físicas",
         "tema": "Tema / reto a resolver", "escenario": "Escenario", "formato": "Formato"}

# Etapas actuales → fase del funnel nuevo. Interesado, Lead iniciado y
# Descartado no existen todavía en Kommo, así que no aparecen aquí.
FASES = {
    110484947: "tipificacion",   # Leads Entrantes
    110486607: "tipificacion",   # Procesando IA
    110486611: "asesor",         # Atender Asesor (transversal)
    110485051: "finalizado",     # Información Recolectada
    110485055: "pendiente_pago", # Pendiente Pago
    PERDIDO:   "perdido",
}
# Pago Realizado y todo lo posterior (producción, envío, posventa) = cierre.
ETAPAS_CIERRE = {110485059, 110485063, 110485067, 110485071, 110742899, 110742903,
                 110742907, 111144335, 111144339, 111144343, 111144347, 111144351,
                 111144355, GANADO}


def leer_env(ruta):
    v = {}
    for l in ruta.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, _, val = l.partition("="); v[k.strip()] = val.strip().strip('"').strip("'")
    return v


class Kommo:
    def __init__(self, sub, token):
        self.base, self.token, self.llamadas = f"https://{sub}.kommo.com/api/v4/", token, 0

    def get(self, ruta):
        for intento in range(5):
            time.sleep(0.16)   # límite: 7 peticiones/seg por integración
            self.llamadas += 1
            req = urllib.request.Request(self.base + ruta, headers={"Authorization": f"Bearer {self.token}"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    cuerpo = r.read()
                    return json.loads(cuerpo) if cuerpo else {}
            except urllib.error.HTTPError as e:
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 ** intento); continue
                raise
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2 ** intento)
        raise RuntimeError(f"Kommo no respondió tras 5 intentos: {ruta[:80]}")

    def paginar(self, ruta, clave, etiqueta):
        pagina, total = 1, 0
        sep = "&" if "?" in ruta else "?"
        while True:
            datos = self.get(f"{ruta}{sep}page={pagina}")
            items = datos.get("_embedded", {}).get(clave, [])
            if not items:
                break
            total += len(items)
            yield from items
            if pagina % 20 == 0:
                print(f"   {etiqueta}: {total:,}…", flush=True)
            if "next" not in datos.get("_links", {}):
                break
            pagina += 1


def dia(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def main():
    inicio = time.time()
    desde = sys.argv[1] if len(sys.argv) > 1 else DESDE_POR_DEFECTO
    ts_desde = int(datetime.strptime(desde, "%Y-%m-%d").timestamp())
    env = leer_env(RAIZ / ".env")
    k = Kommo(env["KOMMO_SUBDOMAIN"], env["KOMMO_LONG_LIVED_TOKEN"])

    try:
        etapas = {}
        for p in k.get("leads/pipelines").get("_embedded", {}).get("pipelines", []):
            if p["id"] == PIPELINE:
                for s in p["_embedded"]["statuses"]:
                    etapas[s["id"]] = {"nombre": s["name"], "orden": s["sort"]}
        usuarios = {u["id"]: u["name"] for u in k.get("users").get("_embedded", {}).get("users", [])}
        motivos = {m["id"]: m["name"] for m in k.get("leads/loss_reasons").get("_embedded", {}).get("loss_reasons", [])}

        print(f"Kommo · leads creados desde {desde}")
        leads = list(k.paginar(f"leads?limit=250&filter[created_at][from]={ts_desde}"
                               f"&filter[pipeline_id][]={PIPELINE}", "leads", "leads"))
        print(f"   {len(leads):,} leads")
        ids = {l["id"] for l in leads}

        def eventos(tipo):
            # Ojo: filter[entity][]=lead hace que los eventos de chat vuelvan vacíos;
            # se filtra por entity_type en código.
            ruta = f"events?limit=100&filter[type][]={tipo}&filter[created_at][from]={ts_desde}"
            return [e for e in k.paginar(ruta, "events", tipo)
                    if e.get("entity_type") == "lead" and e["entity_id"] in ids]

        cambios = eventos("lead_status_changed")
        print(f"   {len(cambios):,} cambios de etapa")
        salientes = eventos("outgoing_chat_message")
        entrantes = eventos("incoming_chat_message")
        print(f"   {len(salientes):,} mensajes nuestros · {len(entrantes):,} del cliente")
    except Exception as e:
        registrar("error", desde, None, str(e), inicio, k.llamadas)
        print(f"✗ {e}"); return 1

    hist = defaultdict(list)
    for e in cambios:
        antes = (e.get("value_before") or [{}])[0].get("lead_status", {})
        despues = (e.get("value_after") or [{}])[0].get("lead_status", {})
        hist[e["entity_id"]].append((e["created_at"], antes.get("id"), despues.get("id")))
    msj_out, msj_in = defaultdict(list), defaultdict(list)
    for e in salientes:
        msj_out[e["entity_id"]].append(e["created_at"])
    for e in entrantes:
        msj_in[e["entity_id"]].append(e["created_at"])

    ahora = int(time.time())
    salida = []
    for l in leads:
        lid, creado = l["id"], l["created_at"]
        campos = {c["field_name"]: (c.get("values") or [{}])[0].get("value") for c in (l.get("custom_fields_values") or [])}
        cambios_l = sorted(hist.get(lid, []))
        # Trayectoria: etapa inicial (antes del primer cambio) + cada cambio.
        tray = [(creado, cambios_l[0][1] if cambios_l else l["status_id"])]
        tray += [(ts, s_nuevo) for ts, _, s_nuevo in cambios_l if s_nuevo]
        out, inn = sorted(msj_out.get(lid, [])), sorted(msj_in.get(lid, []))

        # Tramos por fase: [fase, entrada, salida]. Etapas de cierre se agrupan.
        tramos = []
        for i, (ts, st) in enumerate(tray):
            fin = tray[i + 1][0] if i + 1 < len(tray) else None
            fase = "cierre" if st in ETAPAS_CIERRE else FASES.get(st, "otra")
            if tramos and tramos[-1][0] == fase:
                tramos[-1][2] = fin
            else:
                tramos.append([fase, ts, fin])

        fases = {}
        for fase, ent, sal in tramos:
            if fase in fases:   # re-entrada: solo se mide la primera estancia
                continue
            limite = sal or ahora
            toques = out[bisect_right(out, ent - 1):bisect_right(out, limite)]
            resp = inn[bisect_right(inn, ent - 1):bisect_right(inn, limite)]
            fases[fase] = {"e": ent, "s": sal, "t": len(toques),
                           "d": len({dia(t) for t in toques}), "r": len(resp)}

        # Primera respuesta: del primer mensaje del cliente al primero nuestro después.
        primera = None
        if inn:
            i = bisect_right(out, inn[0])
            if i < len(out):
                primera = out[i] - inn[0]
        ultimo = max(out[-1] if out else 0, inn[-1] if inn else 0)

        # Cliente migrado: el lead NACIÓ ya en una etapa de cierre (importación de
        # pedidos viejos). No es una venta nueva; solo cuenta como venta si entró a
        # cierre desde otra etapa mediante un cambio de etapa real.
        migrado = tray[0][1] in ETAPAS_CIERRE
        ts_pago = None if migrado else next((ts for ts, st in tray[1:] if st in ETAPAS_CIERRE), None)
        formato = campos.get("Formato")
        etiquetas = [t["name"] for t in l.get("_embedded", {}).get("tags", [])]
        salida.append({
            "id": lid, "c": creado, "st": l["status_id"], "mig": migrado,
            "lsa": "importación leadsales" in etiquetas,
            "cl": l.get("closed_at"), "lr": motivos.get(l.get("loss_reason_id")),
            "f": formato, "m": PRECIO.get(formato) if ts_pago else None,
            "u": usuarios.get(l.get("responsible_user_id")),
            "src": campos.get("utm_source"), "cmp": campos.get("utm_campaign"),
            "pg": ts_pago, "fs": fases, "pr": primera,
            "ul": ultimo or None, "ud": ("in" if inn and inn[-1] == ultimo else "out") if ultimo else None,
            "tags": etiquetas,
            # Qué parte del brief está cargada (funnel de WhatsApp del spec).
            "br": {k: bool(campos.get(c)) for k, c in BRIEF.items()},
            "po": out[0] if out else None,   # primer mensaje nuestro = apertura
        })

    TMP.mkdir(parents=True, exist_ok=True)
    destino = TMP / "kommo.json"
    destino.write_text(json.dumps({
        "generado": datetime.now().isoformat(timespec="seconds"), "desde": desde,
        "etapas": etapas, "fases_mapeo": {str(k_): v for k_, v in FASES.items()},
        "etapas_cierre": sorted(ETAPAS_CIERRE), "leads": salida,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ventas = sum(1 for x in salida if x["pg"])
    print(f"✓ {len(salida):,} leads · {ventas:,} ventas → {destino.relative_to(RAIZ)}")
    registrar("ok", desde, str(destino.relative_to(RAIZ)), None, inicio, k.llamadas,
              {"leads": len(salida), "ventas": ventas})
    return 0


def registrar(estado, desde, salida, error, inicio, llamadas, extra=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {"timestamp": datetime.now().isoformat(timespec="seconds"),
             "script": "execution/extraer_kommo.py",
             "inputs": {"desde": desde, "llamadas_api": llamadas, **(extra or {})},
             "outputs": [salida] if salida else [], "status": estado, "error_msg": error,
             "duration_ms": int((time.time() - inicio) * 1000)}
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
