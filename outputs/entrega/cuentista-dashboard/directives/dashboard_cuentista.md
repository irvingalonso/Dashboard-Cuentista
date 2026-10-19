# Dashboard Cuentista (Kommo · Meta Ads · Google Analytics)

## Objetivo
Generar y publicar el tablero de Cuentista: una vista **Semanal** que sigue el spec del cliente (Carlos, 2026-09-25: qué campaña trae qué volumen, cómo convierte y si deja dinero) y tres pestañas de detalle (Kommo contra el funnel del Miro, Meta Ads, Analytics).

## Cuándo usarla
- Piden actualizar, regenerar o publicar el dashboard de Cuentista.
- Piden un corte nuevo de datos de Kommo, Meta Ads o GA4 para Cuentista.
- Cambia el funnel de Kommo (se crean etapas nuevas) → revisar el mapeo de fases.

## Entradas requeridas
- `.env` con: `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (llave secreta propia (p. ej. "dashboard"), solo lectura), `KOMMO_SUBDOMAIN`, `KOMMO_LONG_LIVED_TOKEN`, `META_SYSTEM_USER_TOKEN`, `META_AD_ACCOUNT_CUENTISTA`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`, `GA4_PROPERTY_CUENTISTA`.
- Fecha de inicio del corte (por defecto `2026-01-01`), hasta ayer/hoy.
- Mapeo etapas Kommo → fases del funnel nuevo (definido en `execution/extraer_kommo.py`, constante `FASES`).

## Herramientas / Scripts
- `execution/test_conexion_kommo.py`, `test_conexion_meta.py`, `test_conexion_ga4.py` — pruebas de conexión (solo lectura).
- `execution/generar_token_google.py` — regenera el refresh token de Google si caduca o cambia de cuenta.
- `execution/extraer_kommo.py` — leads, historial de etapas y mensajes → `.tmp/kommo.json`.
- `execution/extraer_meta.py` — insights diarios por anuncio + creatividades (miniaturas en base64) → `.tmp/meta.json`. `--solo-creatividades` refresca solo miniaturas y enlaces.
- `execution/extraer_meta_semanal.py` — gasto, alcance, frecuencia, clics, conversaciones y compras por semana (lunes–domingo), por campaña y conjunto → `.tmp/meta_semanal.json`. Va aparte porque alcance y frecuencia no se suman entre días.
- `execution/empaquetar_entrega.py` — **interno de Rockin**: arma `outputs/cuentista-dashboard.zip` para el cliente (sin `.env`, sin `.tmp/`, sin menciones a otros clientes ni cuentas de Rockin; falla si encuentra alguna). La guía para el cliente está en `entrega/LEEME.md`.
- `execution/test_conexion_supabase.py` — prueba de conexión con Supabase (lista tablas, conteos y columnas; no muestra datos de clientes).
- `execution/extraer_supabase.py` — pagos del sitio (`checkout_sessions`): fecha, estado, monto, físicos/digitales, cupón y UTM, sin datos personales → `.tmp/supabase.json`.
- `execution/armar_semanal.py` — arma los bloques semanales (lo importa el constructor).
- `execution/parametros_tablero.json` — precios, costos de producción, Stripe, metas, umbrales de alertas y etiquetas, y fuentes web que cuentan como WhatsApp. **Editar aquí, no en el código.**
- `execution/extraer_ga4.py` — funnel web del spec por canal (`funnel_canal`) · sesiones/compras diarias por canal, dispositivo, hora, página de entrada y embudo del sitio, más el funnel web y las compras por campaña (`sessionCampaignName` = nombre de la campaña de Meta) → `.tmp/ga4.json`.
- `execution/construir_dashboard.py` + `execution/plantilla_dashboard.html` — une todo en `outputs/dashboard.html`.
- APIs: Kommo API v4 (Bearer), Meta Graph API v23.0, GA4 Data API v1beta. Todas de solo lectura y sin costo.

## Pasos
1. Correr las 3 pruebas de conexión. Si alguna falla, resolver antes de extraer (ver casos extremos).
2. `python3 execution/extraer_kommo.py [YYYY-MM-DD]`
3. `python3 execution/extraer_meta.py [YYYY-MM-DD]` y `python3 execution/extraer_meta_semanal.py [N semanas]`
4. `python3 execution/extraer_ga4.py [YYYY-MM-DD]` y `python3 execution/extraer_supabase.py`
5. `python3 execution/construir_dashboard.py`
6. Publicar `outputs/dashboard.html` como página privada de Claude (Artifact), en la misma URL que la versión anterior, con la capacidad `db` (anotaciones del equipo). No editar el HTML a mano. Las anotaciones viven en la base del artefacto (colección `anotaciones`) y sobreviven a cada republicación.

## Salidas
- `outputs/dashboard.html` — dashboard autocontenido (datos + miniaturas incrustados), filtros de fecha en el navegador.
- Página privada en claude.ai (la comparte el usuario).

## Reglas de negocio
- **Fuentes por métrica (acordado 2026-10-01)**: el **valor y el número de ventas** salen de Supabase (`checkout_sessions` con estado `completed` o `paid`, monto cobrado real); las **etapas del funnel** salen de Kommo (WhatsApp) y GA4 (web). La pestaña Resumen ya usa Supabase; la vista Semanal y las de detalle siguen con su base anterior hasta decidir migrarlas.
- **Margen real** (Resumen) = ingreso cobrado − producción por cuento ($120 físico / $15 digital) − Stripe ($3 + 3.6% por pago) − inversión en Meta. La comisión de Stripe se aplica a todo pago, aunque las transferencias no la pagan: el margen sale ligeramente conservador.
- **Venta** = lead que pasó alguna vez por "Pago Realizado" (id 110485059), aunque siga en producción o envío. "Lead ganado" casi no se usa.
- **Monto de venta**: el `price` de Kommo viene en 0 → se estima por el campo Formato: Digital $149 MXN, Físico $449 MXN. Sin formato → se cuenta la venta pero no el monto.
- **Fases del funnel nuevo** (mapeo sobre las etapas actuales):
  - Tipificación IA = Leads Entrantes + Procesando IA
  - Lead finalizado = Información Recolectada
  - Pendiente de pago = Pendiente Pago
  - Cierre = Pago Realizado y todas las etapas de producción/entrega/posventa + Lead ganado
  - Asesor humano (transversal) = Atender Asesor — según el funnel nuevo debe ser excepción
  - Perdido (transversal) = Lead perdido
  - Interesado, Lead iniciado y Descartado **no existen en Kommo**: no se miden; el dashboard lo indica.
- **Cadencias del funnel nuevo** contra las que se compara: Tipificación 3 toques en 3 días distintos, sin respuesta al día 3 → Perdido; Lead finalizado seguimiento 3 días; Pendiente de pago 5 días con hasta 2 toques/día; Perdido → reimpacto a los 7–14 días.
- **Meta**: el "resultado" depende del objetivo — ventas (OUTCOME_SALES) = compras web; leads (OUTCOME_LEADS) = conversaciones de WhatsApp. ROAS solo se calcula para campañas de ventas; el ROAS genérico usa inversión total.
- **GA4**: la conversión se mide con el evento `purchase`, NUNCA con "eventos clave" (ver casos extremos).

## Vista Semanal (spec del cliente)
- **Orden de lectura**: alertas → resumen (7 tiles con chispa de 6 semanas) → tendencia → campañas (tabla que filtra) → funnels WhatsApp y Web por separado.
- **Controles**: semana (por defecto la última cerrada), comparar contra semana anterior o rolling 4, cobertura de atribución, notas de diseño.
- **Destino por objetivo de Meta**: OUTCOME_LEADS = WhatsApp (ámbar); OUTCOME_SALES/TRAFFIC = Web (azul). El color marca destino, nunca jerarquía.
- **Base de ventas (provisional, acordado 2026-09-28)**: WhatsApp = entrada a Pago Realizado en Kommo (sin migrados ni movimientos en bloque); Web = compras de GA4. Cuando exista la base conciliada con Stripe/BBVA, reemplazar esta fuente.
- **Canal por punto de entrada**: compras web con `cuentista / sasu` o `l.wl.co` (link del asesor) son WhatsApp, no Web (`whatsapp_en_web` en parámetros). Se asume que ya están en Kommo, así que no se suman otra vez.
- **Atribución**: Web = compra de GA4 cuya campaña coincide con una campaña de Meta. WhatsApp = no se liga a campaña (Kommo sin `ctwa_clid`); solo se asigna cuando hay UNA campaña de WhatsApp activa esa semana, marcado con asterisco. Nunca se reparte.
- **Precios (acordado 2026-09-28)**: los del spec, físico $350 / digital $99. Producción $120 / $15, Stripe $3 + 3.6%. Pendiente confirmar con finanzas; el ticket real en GA4 es ~$367 / ~$71 y el bot ofrece $449 / $149.
- **Fórmulas**: ticket = %fís×350 + %dig×99; margen unitario = ticket − producción − $3 − 3.6%×ticket; margen de contribución = margen unitario − CAC; CAC = gasto ÷ ventas atribuidas; ROAS piso = ingreso atribuido ÷ gasto, techo = ingreso de toda la base ÷ gasto; cobertura = ventas atribuidas ÷ ventas de la base; LPV% web = sesiones GA4 de la campaña ÷ clics al enlace de Meta; pérdida por etapa = (nᵢ₋₁ − nᵢ) ÷ n₀ × 100.
- **Funnel WhatsApp** (Kommo, cohorte por semana de entrada, sin Leadsales ni migrados): Conversación iniciada (lead creado) · Apertura del asesor (primer mensaje nuestro) · Tema definido (campo Tema) · Brief completo (nombre, edad, rasgos, tema y escenario) · Formato elegido (reemplaza "Precio presentado", que Kommo no registra) · Cierre solicitado (Pendiente Pago) · Pago confirmado. Escalera: quien llegó a un escalón cuenta en los anteriores.
- **Funnel Web** (GA4 por campaña): Landing view (sesiones) · Configurador iniciado (`story_config_started`) · Brief completo (`story_config_step` en /crea-tu-historia/resumen-y-confirmacion) · Lead (sin medir: falta evento `lead`) · Checkout (`begin_checkout`) · Pago (`purchase`).
- **Protecciones del spec**: tasa siempre con su absoluto; promedio de 6 semanas al lado; renglón en gris bajo 20 casos; las dos mayores pérdidas en rojo; aviso cuando el gasto se mueve >30%.
- **Pendiente del spec**: modo A/B (hoy hay una sola campaña por destino); desglose a nivel anuncio (se queda en conjunto).

## Casos extremos y errores conocidos
- **Correr SIEMPRE los 4 extractores antes de publicar.** Las pestañas Resumen, Meta Ads y Analytics usan el corte diario de Meta (`extraer_meta.py`); la vista Semanal usa el semanal. Si solo se corre uno, las otras pestañas muestran días en cero que no lo son (pasó el 2026-09-28: diario hasta el 23 → pauta "en cero" del 24 en adelante). `construir_dashboard.py` avisa si alguna fuente quedó más de 2 días atrás.
- **GA4 "eventos clave" inflados**: `page_view`, `session_start` y `first_visit` están marcados como clave en la propiedad → cada visita cuenta como conversión. Usar `purchase`/`ecommercePurchases`.
- **GA4 por canal con fecha**: si se pide `date` + canal, hay que agregar en código; si no, cada canal aparece repetido por día (error del dashboard anterior en Netlify).
- **GA4 403**: correr `test_conexion_ga4.py`; al fallar lista las propiedades visibles con su ID real. Property ID correcto: `502149439`.
- **Meta #200 "Ad account owner has NOT grant ads_read"**: el usuario del sistema del token no tiene la cuenta asignada. Asignar la cuenta publicitaria al usuario del sistema dueño del token, con permiso para ver rendimiento.
- **Kommo**: rate limit 7 peticiones/seg por integración → el extractor pausa entre páginas. Eventos máx. 100 por página. Si 401 → regenerar token de larga duración en la integración "Dashboard Rockin".
- **Miniaturas de Meta**: la página publicada no carga imágenes externas → se incrustan en base64. Pedir `creative.thumbnail_width(400).thumbnail_height(400){thumbnail_url}`: sin el modificador la miniatura es de 64 px.
- **Meta insights diarios a nivel anuncio**: pedir el rango completo (9 meses) con `time_increment=1` se cuelga; el extractor pide mes a mes (~2–3 min por mes).
- **Kommo eventos de chat**: `filter[entity][]=lead` devuelve vacío para `incoming/outgoing_chat_message` → filtrar `entity_type` en código.
- **Kommo empezó a operar el 2026-08-04.** No hay leads antes. Dos grupos especiales:
  - **Clientes migrados** (~930): nacieron ya en etapas de posventa (Pendiente NPS, Enviado…). NO son ventas nuevas → `mig=true`, se excluyen del funnel.
  - **Leads de Leadsales** (etiqueta "importación leadsales", ~4,600): entran a diario; ~3,400 se marcaron Perdido en bloque el 2026-09-09. El dashboard los deja filtrar (Origen) y señala la limpieza masiva.
- **Kommo sin UTM ni motivo de pérdida**: los campos utm_* vienen vacíos en todos los leads y casi ningún Perdido tiene motivo → no se puede cruzar lead con campaña de Meta. Es un hallazgo para el cliente, no un error del extractor.
- **GA4 rebote ~1% (falso)**: como `page_view`/`session_start` son eventos clave, toda sesión cuenta como "con interacción". El dashboard lo marca como no confiable hasta que el cliente deje solo `purchase` como clave.
- **Meta landing_page_view < add_to_cart**: el evento de visita del píxel no está bien instalado; el embudo de Meta omite ese paso cuando pasa.
- **Meta: mismo creativo en varios conjuntos** con distinto `ad_id` → la galería agrupa por nombre de anuncio.
- **Kommo por defecto "Kommo directo"**: el filtro Origen arranca excluyendo Leadsales porque su flujo tiene firmas de migración (asesor a los 12 min, perdidos y cierres en bloque).
- **GA4 purchase > begin_checkout**: hay más eventos `purchase` que `begin_checkout` → probable doble disparo del evento de compra. El dashboard lo avisa.

## Historial de cambios
- 2026-10-02: entrega del proyecto al cliente para que lo opere con su propio Claude Code y sus propias llaves (`empaquetar_entrega.py` + `entrega/LEEME.md`).
- 2026-10-01: Supabase como base de ventas real del Resumen (KPIs de ventas, ingreso, ticket, costo por venta, ROAS real, margen y pagos completados; panel de ventas reales por mes; ventas y costo por venta semanales). Nuevos `test_conexion_supabase.py` y `extraer_supabase.py`.
- 2026-09-28: nueva pestaña **Resumen** (primera): ventas, inversión, costo por venta, ingreso estimado/ROAS, margen y checkout→compra con comparación contra el periodo anterior; hasta 5 hallazgos priorizados entre Kommo, Meta y GA4; caminos de WhatsApp y web con costo por paso; ventas y costo por venta por semana; anuncios que más traen. En **Meta Ads**, las campañas de conversiones y las de WhatsApp van en secciones separadas, cada una con sus KPIs y una tabla campaña → conjunto → anuncio desplegable (frecuencia = promedio semanal ponderado por gasto).
- 2026-09-28: a pedido de María (cliente), la pestaña Analytics muestra el **funnel del formulario** (Inicio · Paquete · Aventura · Protagonista · Personalización · Resumen · Checkout · Compra; sesiones de GA4 por paso, `story_config_step` por página) en forma de banda, con filtro por canal y comparación contra el periodo anterior, más KPIs: frecuencia, CPA, impresiones, CPM, CTR, ROAS (Meta) y sesiones iniciadas y carritos (GA4). Reemplaza al Funnel Web del spec en esa pestaña; el del spec sigue en la vista Semanal.
- 2026-09-28: la pestaña Analytics usa el Funnel Web del spec (mismas etapas y columnas que la vista Semanal), sobre todo el tráfico del sitio y filtrable por canal; compara contra el periodo anterior de igual largo y excluye las compras del link del asesor. Reemplaza el embudo por conteo de eventos.
- 2026-09-28: versión 2. Vista Semanal según el spec de Carlos como pestaña principal; las 3 pestañas anteriores quedan como detalle. Nuevos: `extraer_meta_semanal.py`, `armar_semanal.py`, `parametros_tablero.json`, campos del brief en Kommo, funnel web por campaña en GA4, anotaciones compartidas.
- 2026-09-23: creación. Rediseño del dashboard de Netlify (rechazado por exceso de información sin conclusiones) en 3 pestañas guiadas por el funnel nuevo.
