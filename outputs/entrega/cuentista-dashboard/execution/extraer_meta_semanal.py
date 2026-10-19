#!/usr/bin/env python3
"""
Extrae de Meta Ads el rendimiento SEMANAL (lunes a domingo) por campaña y por
conjunto de anuncios, para el tablero semanal del spec. Solo lee.

Va aparte de extraer_meta.py porque alcance y frecuencia NO se pueden sumar
entre días: hay que pedirlos ya agregados por semana. Se pide una semana por
llamada para evitar el corte por tiempo de Meta (subcode 1504018).

Uso:  python3 execution/extraer_meta_semanal.py [N semanas, por defecto 13]
Escribe  .tmp/meta_semanal.json
"""
import json, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extraer_meta import (COMPRA, CONVERSACION, LANDING, RAIZ, TMP, LOGS, accion, graph,
                          leer_env, todas)

CAMPOS = ("campaign_id,campaign_name,adset_id,adset_name,spend,impressions,reach,frequency,"
          "clicks,inline_link_clicks,actions,action_values")


def fila(f, nivel):
    acts, vals = f.get("actions"), f.get("action_values")
    return {
        "id": f[f"{nivel}_id"], "campana": f["campaign_id"],
        "gasto": round(float(f.get("spend", 0) or 0), 2),
        "imp": int(f.get("impressions", 0) or 0), "alcance": int(f.get("reach", 0) or 0),
        "frec": round(float(f.get("frequency", 0) or 0), 3),
        "clics_enlace": int(f.get("inline_link_clicks", 0) or 0),
        "lpv": int(accion(acts, LANDING + ["omni_landing_page_view"])),
        "conversaciones": int(accion(acts, CONVERSACION)),
        "compras": int(accion(acts, COMPRA)), "valor": round(accion(vals, COMPRA), 2),
    }


def main():
    inicio = time.time()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 13
    env = leer_env(RAIZ / ".env")
    token, cuenta = env["META_SYSTEM_USER_TOKEN"], env["META_AD_ACCOUNT_CUENTISTA"]
    hoy = date.today()
    lunes = hoy - timedelta(days=hoy.weekday())
    semanas = [lunes - timedelta(weeks=i) for i in range(n - 1, -1, -1)]

    try:
        print(f"Meta semanal · cuenta {cuenta} · {n} semanas desde {semanas[0]}")
        campanas = {c["id"]: {"nombre": c["name"], "objetivo": c.get("objective"),
                              "estado": c.get("effective_status")}
                    for c in todas(graph(f"act_{cuenta}/campaigns", token,
                                         fields="id,name,objective,effective_status", limit=200), token)}
        filas = {"campaign": [], "adset": []}
        conjuntos = {}
        for ini in semanas:
            fin = min(ini + timedelta(days=6), hoy)
            rango = json.dumps({"since": ini.isoformat(), "until": fin.isoformat()})
            for nivel in ("campaign", "adset"):
                for f in todas(graph(f"act_{cuenta}/insights", token, level=nivel, limit=200,
                                     time_range=rango, fields=CAMPOS), token):
                    r = fila(f, nivel)
                    if r["gasto"] <= 0 and r["imp"] == 0:
                        continue
                    r["semana"] = ini.isoformat()
                    filas[nivel].append(r)
                    if nivel == "adset":
                        conjuntos[r["id"]] = {"nombre": f.get("adset_name"), "campana": f["campaign_id"]}
            print(f"   semana {ini}: {len(filas['campaign'])} filas de campaña acumuladas", flush=True)
    except Exception as e:
        registrar("error", n, None, str(e), inicio)
        print(f"✗ {e}"); return 1

    TMP.mkdir(parents=True, exist_ok=True)
    destino = TMP / "meta_semanal.json"
    destino.write_text(json.dumps({
        "generado": datetime.now().isoformat(timespec="seconds"), "cuenta": cuenta,
        "semanas": [s.isoformat() for s in semanas], "semana_en_curso": lunes.isoformat(),
        "campanas": campanas, "conjuntos": conjuntos,
        "por_campana": filas["campaign"], "por_conjunto": filas["adset"],
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✓ {len(filas['campaign'])} filas campaña · {len(filas['adset'])} filas conjunto → "
          f"{destino.relative_to(RAIZ)}")
    registrar("ok", n, str(destino.relative_to(RAIZ)), None, inicio)
    return 0


def registrar(estado, n, salida, error, inicio):
    LOGS.mkdir(parents=True, exist_ok=True)
    linea = {"timestamp": datetime.now().isoformat(timespec="seconds"),
             "script": "execution/extraer_meta_semanal.py", "inputs": {"semanas": n},
             "outputs": [salida] if salida else [], "status": estado, "error_msg": error,
             "duration_ms": int((time.time() - inicio) * 1000)}
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
