#!/usr/bin/env python3
"""
Actualización completa del dashboard: corre los 5 extractores en orden y arma
outputs/dashboard.html. Es el paso que se ejecuta cada día (tarea programada).

Si un extractor falla, sigue con los demás y al final lo reporta: así un problema
en una sola fuente no deja todo el dashboard sin actualizar. Termina con código 1
si algo falló, para que quien lo ejecute sepa que debe revisar antes de publicar.

Uso:  python3 execution/actualizar_todo.py
"""
import json, subprocess, sys, time
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LOGS = RAIZ / ".tmp" / "logs"
PASOS = ["extraer_supabase.py", "extraer_ga4.py", "extraer_meta_semanal.py", "extraer_kommo.py",
         "extraer_meta.py", "construir_dashboard.py"]


def main():
    inicio = time.time()
    resultados = []
    for p in PASOS:
        t0 = time.time()
        print(f"▶ {p}", flush=True)
        r = subprocess.run([sys.executable, str(RAIZ / "execution" / p)], cwd=RAIZ,
                           capture_output=True, text=True, timeout=3600)
        salida = (r.stdout + r.stderr).strip().splitlines()
        resumen = next((l for l in reversed(salida) if l.startswith(("✓", "✗", "⚠"))), salida[-1] if salida else "")
        avisos = [l for l in salida if l.startswith("⚠")]
        ok = r.returncode == 0
        print(f"  {'✓' if ok else '✗'} {resumen}  ({time.time() - t0:.0f} s)", flush=True)
        for a in avisos:
            print(f"  {a}", flush=True)
        resultados.append({"paso": p, "ok": ok, "resumen": resumen[:200], "avisos": avisos})
    fallas = [r["paso"] for r in resultados if not r["ok"]]
    atraso = any("Fuentes atrasadas" in a for r in resultados for a in r["avisos"])
    estado = "ok" if not fallas and not atraso else "error"
    print(("\n✓ Todo actualizado. Listo para publicar." if estado == "ok" else
           f"\n✗ Revisar antes de publicar: {', '.join(fallas) or 'fuentes atrasadas'}"), flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / f"{date.today().isoformat()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": datetime.now().isoformat(timespec="seconds"),
                            "script": "execution/actualizar_todo.py", "inputs": {"pasos": PASOS},
                            "outputs": ["outputs/dashboard.html"], "status": estado,
                            "error_msg": ", ".join(fallas) or ("fuentes atrasadas" if atraso else None),
                            "duration_ms": int((time.time() - inicio) * 1000)}, ensure_ascii=False) + "\n")
    return 0 if estado == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
