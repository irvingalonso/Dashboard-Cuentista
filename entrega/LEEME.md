# Dashboard Cuentista: guía para usarlo con Claude Code

Esta carpeta trae todo lo necesario para que **tú mismo actualices el dashboard y le pidas cambios a Claude**: otra gráfica, otro indicador, otro cálculo. Claude ya sabe cómo está construido, porque lee las instrucciones de esta carpeta (`CLAUDE.md` y `directives/`).

**Qué hay dentro**
- `outputs/dashboard.html`: el dashboard con los últimos datos. Puedes abrirlo con doble clic.
- `execution/`: los programas que bajan los datos de Kommo, Meta, Google Analytics y Supabase y arman el dashboard.
- `directives/dashboard_cuentista.md`: el manual del dashboard (qué mide, cómo y de dónde sale cada número).
- `CLAUDE.md`: las reglas y lo aprendido durante la construcción. Claude lo lee solo.
- `.env.example`: la plantilla donde van **tus** llaves de acceso.

---

## Paso 1. Instalar Claude Code
1. Descarga la app de escritorio de Claude desde **claude.com/download** e inicia sesión con tu cuenta.
2. Abre la pestaña **Code**.
3. Necesitas **Python 3** en tu computador. Si no lo tienes, pídele a Claude: *"Revisa si tengo Python 3 instalado y ayúdame a instalarlo"*.

## Paso 2. Abrir la carpeta
1. Descomprime este archivo en una carpeta que no vayas a mover (por ejemplo, Documentos).
2. En Claude Code, elige **abrir carpeta** y selecciona `cuentista-dashboard`.
3. Escribe: *"Lee el CLAUDE.md y la directiva del dashboard y dime qué necesitas para empezar"*.

## Paso 3. Crear tus llaves de acceso
El dashboard lee datos de 4 sistemas y necesita una llave de solo lectura de cada uno. **Son tuyas: no las compartas con nadie ni las pegues en un chat.** Se guardan solo en un archivo llamado `.env` dentro de la carpeta.

Para cada una, pídele a Claude que te guíe, por ejemplo: *"Ayúdame paso a paso a sacar la llave de Kommo"*. En resumen:

| Sistema | Qué necesitas | Dónde se saca |
|---|---|---|
| **Kommo** | Subdominio + token de larga duración | Kommo → Configuración → Integraciones → crear una integración privada → *Llaves y alcances* → **Generar token de larga duración** |
| **Meta Ads** | Token de un usuario del sistema con permiso `ads_read` | Business Manager de Cuentista Mx → Usuarios del sistema → asignarle la cuenta publicitaria con **Ver rendimiento** → **Generar token** (permiso `ads_read`, caducidad "Nunca") |
| **Google Analytics 4** | Client ID + Client secret + refresh token | Google Cloud → crear un cliente OAuth tipo **Aplicación de escritorio** y activar la *Google Analytics Data API*. Luego Claude corre `generar_token_google.py`, que abre tu navegador para que autorices con la cuenta que ve GA4 |
| **Supabase** | URL del proyecto + llave secreta | Supabase → Project Settings → **API Keys** → *Secret keys* → **crear una llave nueva** (por ejemplo "dashboard") |

Cuando las tengas, pídele a Claude: *"Crea el archivo .env a partir de .env.example y ábremelo para pegar las llaves"*. Pega cada llave después del `=` y guarda.

## Paso 4. Probar que todo conecta
Pídele a Claude: *"Corre las pruebas de conexión de Kommo, Meta, GA4 y Supabase"*.
Si alguna falla, Claude te dirá por qué y cómo arreglarlo. Los errores más comunes ya están documentados en la directiva.

## Paso 5. Actualizar y publicar el dashboard
Pídele a Claude: *"Actualiza el dashboard con los datos de hoy y publícalo"*.
Claude correrá los 5 extractores, armará `outputs/dashboard.html` y lo publicará como página privada en tu cuenta de Claude. La primera vez te dará un enlace nuevo; las siguientes veces actualiza ese mismo enlace.

> Siempre deja que Claude corra **todos** los extractores antes de publicar. Si una fuente queda atrasada, el dashboard muestra días en cero que no lo son (el programa te avisa con "⚠ Fuentes atrasadas").

## Paso 6. Pedir cambios
Escríbele a Claude como le hablarías a una persona. Ejemplos:
- *"En la pestaña Resumen agrega una gráfica de ingreso por semana."*
- *"Quiero ver el costo por venta de cada anuncio en Meta Ads."*
- *"Cambia el costo de producción del cuento físico a $140."*
- *"Oculta la pestaña Semanal."*
- *"¿Por qué bajaron las ventas esta semana?"*

Claude hará el cambio en los programas (no en el archivo final), volverá a generar el dashboard y te lo mostrará antes de publicarlo.

**Consejos**
- Los precios, costos de producción, comisiones, metas y umbrales están en `execution/parametros_tablero.json`. Cambiarlos ahí es lo más seguro; pídeselo a Claude.
- No edites `outputs/dashboard.html` a mano: se reescribe cada vez que se actualiza.
- Si algo falla, pídele a Claude: *"Revisa el último log en .tmp/logs y dime qué pasó"*.
