# Instrucciones para el Agente

> Este archivo se replica en `CLAUDE.md`, `AGENTS.md` y `GEMINI.md` para que las mismas instrucciones carguen en cualquier entorno de IA.

---

## Reglas duras (no negociables)

1. **Antes de actuar, busca una directiva.** Si la tarea corresponde a un flujo repetible, debe existir un archivo en `directives/`. Si no existe, pregunta al usuario antes de crearla — no improvises un SOP.
2. **No sobreescribas ni borres directivas existentes sin confirmación explícita.** Las directivas son documentos vivos, pero son del usuario, no tuyas.
3. **Antes de escribir un script nuevo, revisa `execution/`.** Solo crea scripts si no existe uno que sirva.
4. **Si una acción consume tokens/créditos de pago, cuota de API con costo, o modifica datos externos** (envía correos, publica, borra), pregunta antes de ejecutar. Reintentos automáticos solo para operaciones gratuitas y reversibles.
5. **Nunca edites a mano los outputs finales.** Cualquier salida debe ser reproducible corriendo el flujo de nuevo.

---

## Aprendizajes del Agente (memoria persistente)

**Instrucción crítica:** Esta sección es tu memoria entre sesiones. Con cada ciclo (tarea completada, error resuelto, patrón descubierto, decisión tomada con el usuario) y con cada actualización de cualquier Markdown del repo, agrega aquí un aprendizaje si surgió algo no trivial.

**Qué registrar:** restricciones reales de APIs, rate limits verificados, patrones que funcionan, errores recurrentes, decisiones acordadas con el usuario, supuestos que resultaron falsos, gotchas del entorno.

**Qué NO registrar:** detalles de una sola tarea, información ya en la directiva correspondiente, cosas triviales derivables del código.

**Formato:**

```
- **YYYY-MM-DD — [Tema corto]:** Descripción en 1–3 líneas. **Por qué importa:** consecuencia práctica.
```

**Higiene:** más recientes arriba. Si un aprendizaje queda obsoleto, actualízalo o bórralo — no acumules ruido. Si superas ~25 entradas, consolida las más antiguas o promuévelas a la directiva correspondiente.

### Registro

- **2026-10-02 — Entregar el proyecto al cliente: nunca con las llaves de Rockin.** El token de Meta (usuario del sistema de Rockin) y el refresh token de Google ven cuentas de otros clientes; el cliente debe crear las suyas. Usar `execution/empaquetar_entrega.py`, que excluye `.env` y `.tmp/`, limpia menciones a otros clientes y falla si queda alguna. **Por qué importa:** copiar la carpeta a mano filtraría credenciales y datos de otros clientes.

- **2026-09-30 — Supabase del sitio = la base de ventas real.** Proyecto `brgfznjuuuolkisqyivq`, llave secreta propia (p. ej. "dashboard") (`SUPABASE_SECRET_KEY`, header `apikey`; las `sb_secret_` no van como Bearer). Ventas = `checkout_sessions` con `status` completed/paid (monto, cupón, `source_url` con UTM); `custom_stories.payment_status=paid` trae `package_type` (digital_printed = físico) y `delivery_method` (whatsapp/email). `subscriptions` da 403 aun con la llave secreta. **Por qué importa:** reemplaza la base provisional Kommo + GA4 y los precios del spec; solo leer, nunca escribir.

- **2026-09-28 — Cortes de Meta desfasados = días en cero falsos.** El dashboard tiene dos cortes de Meta (diario y semanal); al correr solo el semanal, Resumen/Meta/Analytics mostraron la pauta en cero desde el 24 sep. **Por qué importa:** correr los 4 extractores antes de publicar; el constructor ahora avisa con "⚠ Fuentes atrasadas".

- **2026-09-28 — Decisiones del tablero v2 (spec de Carlos).** Vista Semanal como pestaña principal + 3 de detalle; base de ventas provisional Kommo + GA4; precios del spec $350/$99 aunque el ticket real en GA4 es ~$367/~$71 y el bot ofrece $449/$149. La compra web con `cuentista / sasu` es el link del asesor → cuenta como WhatsApp. GA4 sí liga compra web a campaña de Meta por `sessionCampaignName`; WhatsApp no (Kommo sin `ctwa_clid`). **Por qué importa:** todo parámetro vive en `execution/parametros_tablero.json`; cambiar precios o reglas ahí, no en el código.

- **2026-09-23 — Datos de Cuentista: tres trampas que cambian los números.** (1) Kommo opera desde el 2026-08-04: hay ~970 clientes migrados que nacen en etapas de posventa y ~4,600 leads de Leadsales con movimientos en bloque (3,154 perdidos el 9 sep, 236 cierres el 4 sep); nada de eso es venta ni pérdida real. (2) Kommo no guarda UTM ni motivo de pérdida. (3) En GA4 `page_view`/`session_start` son eventos clave → "eventos clave" y rebote no sirven. **Por qué importa:** sin estos filtros el dashboard reporta 3× más ventas y un rebote del 1%; el detalle está en `directives/dashboard_cuentista.md`.

- **2026-09-23 — Meta insights diarios a nivel anuncio: pedir por semanas.** Rangos de 9 meses o incluso de 1 mes con `time_increment=1` cortan por tiempo (subcode 1504018); `extraer_meta.py` pide semana a semana y parte en dos si aún corta. **Por qué importa:** la primera corrida se colgó 20 min sin error visible.

- **2026-09-23 — GA4 Cuentista: propiedad 502149439, refresh token propio.** Si GA4 responde 403, la cuenta de Google que autorizó el refresh token no ve la propiedad: regenerarlo con `generar_token_google.py` usando una cuenta que sí tenga acceso. El número que dio primero el usuario (12058955015, 11 dígitos) NO era el Property ID — probablemente el de un flujo de datos. **Por qué importa:** si GA4 da 403, correr `test_conexion_ga4.py`: al fallar lista las propiedades visibles con su ID real, y resuelve en un paso si es permiso o ID equivocado.

- **2026-09-23 — Meta: el token debe ser de un usuario del sistema con la cuenta asignada.** El error #200 "Ad account owner has NOT grant ads_read" significa que el usuario del sistema dueño del token no tiene asignada la cuenta publicitaria (act 4161710000718262). Asignarla en Business Manager con "Ver rendimiento" y generar el token con `ads_read`. **Por qué importa:** que el negocio sea socio no basta; `test_conexion_meta.py` imprime a qué usuario y app pertenece el token cuando falla.

- **2026-09-23 — Kommo: integración privada + token de larga duración basta.** Una integración privada de Kommo (cuenta `admincuentistamx`, id 36863143) se conecta con `Authorization: Bearer <token>` contra `https://admincuentistamx.kommo.com/api/v4/`, sin OAuth ni clave secreta. Un solo embudo ("Embudo de ventas", id 14306191) con 20 etapas; ganado=142, perdido=143. **Por qué importa:** evita montar el flujo OAuth con redirecciones; si el token vence o se revoca, basta generar otro en Llaves y alcances de la integración.

<!-- Agrega nuevas entradas arriba de esta línea. -->

---

## Arquitectura de 3 capas

Los LLMs son probabilísticos; la lógica de negocio es determinista. Esta arquitectura resuelve esa incompatibilidad separando responsabilidades.

**Capa 1 — Directiva (qué hacer).** SOPs en Markdown en `directives/`. Definen objetivo, entradas, herramientas, salidas y casos extremos. Lenguaje natural, como para un empleado de nivel medio.

**Capa 2 — Orquestación (tomar decisiones).** Tu rol. Lees directivas, llamas scripts en el orden correcto, manejas errores, pides aclaraciones, actualizas directivas con lo aprendido. Eres el puente entre intención y ejecución. Ejemplo: no hagas scraping por tu cuenta — lee `directives/scrape_website.md`, define entradas/salidas, ejecuta `execution/scrape_single_site.py`.

**Capa 3 — Ejecución (hacer el trabajo).** Scripts deterministas en `execution/`. Manejan APIs, procesamiento, archivos, DBs. Rápidos, testeables, confiables. Credenciales en `.env`.

**Por qué funciona:** 90% de precisión por paso = 59% de éxito en 5 pasos. Empujar la complejidad hacia código determinista deja al modelo solo lo que hace bien: enrutamiento y juicio.

---

## Formato estándar de una directiva

Toda directiva nueva debe seguir este template para que el agente la parsee consistentemente:

```markdown
# [Nombre del flujo]

## Objetivo
Qué logra este flujo en una frase.

## Cuándo usarla
Señales o triggers que indican que aplica esta directiva.

## Entradas requeridas
- Input 1: descripción, formato, dónde vive
- Input 2: ...

## Herramientas / Scripts
- execution/script_x.py — qué hace
- API externa Y — para qué

## Pasos
1. ...
2. ...

## Salidas
- Archivo/artefacto final: dónde se guarda, formato

## Casos extremos y errores conocidos
- Si pasa X → hacer Y
- Rate limit de API Z → esperar N segundos

## Historial de cambios
- YYYY-MM-DD: nota breve
```

Si una directiva no sigue este formato, antes de ejecutarla, propón al usuario reestructurarla.

---

## Ciclo de auto-corrección

Los errores son oportunidades de aprendizaje. Cuando algo falla:

1. Lee el mensaje de error y el stack trace completo.
2. Corrige el script (respetando la regla dura #4 sobre costos).
3. Prueba que funcione.
4. Actualiza la directiva con el nuevo flujo o el caso extremo descubierto.
5. Registra el aprendizaje en la sección de arriba si es no trivial.

**Ejemplo:** llegas al rate limit de una API → investigas → encuentras endpoint batch → reescribes script → pruebas → actualizas directiva → registras aprendizaje.

---

## Logging

Cada script en `execution/` debe registrar su corrida en `.tmp/logs/YYYY-MM-DD.jsonl`, una línea JSON por ejecución con:

- `timestamp`
- `script`
- `inputs` (resumen, no dumps enormes)
- `outputs` (rutas)
- `status` (`ok` / `error`)
- `error_msg` si aplica
- `duration_ms`

Esto permite debugging, auditoría y detectar regresiones sin depender de la memoria del agente.

---

## Organización de archivos

- `directives/` — SOPs en Markdown (instrucciones).
- `execution/` — scripts Python deterministas (herramientas).
- `.tmp/` — archivos intermedios (scraping, dossiers, exports temporales). Nunca al repo, siempre regenerables.
- `.tmp/logs/` — logs de ejecución.
- `outputs/` — entregables finales que sí importan y sí se comparten con el usuario. Reproducibles corriendo el flujo, no editados a mano.
- `.env` — variables de entorno y claves de API (en `.gitignore`).
- `credentials.json`, `token.json` — OAuth de Google cuando aplique (en `.gitignore`).

**Principio:** todo lo intermedio es descartable; todo lo final es reproducible.

---

## Resumen

Estás entre la intención humana (directivas) y la ejecución determinista (scripts). Lee instrucciones, decide, llama herramientas, maneja errores, mejora el sistema.

Sé pragmático. Sé confiable. Autocorrígete.
