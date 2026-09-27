# Lectora OMR — Rediseño profesional 2026

Esta copia conserva el procesamiento OMR, las rutas del servidor, la gestión de
claves, el registro, la plantilla, la cámara y la exportación. Los cambios se
concentran en la presentación web y Android.

## Mejoras incluidas

- Cabecera web con escáner 3D animado y estado del sistema.
- Diseño adaptable para escritorio, tablet y teléfono.
- Paneles con profundidad, cristal, iluminación y mejor jerarquía visual.
- Navegación fija y controles táctiles más claros.
- Animaciones respetuosas con la preferencia de movimiento reducido.
- Tema Android unificado con la interfaz web.
- Portada Android tridimensional, tarjetas modernas y transiciones suaves.
- Cámara con barrido luminoso, indicadores de estado y disparador mejorado.
- Galería de lotes, cuadros de diálogo e icono de aplicación renovados.
- Firma visual de derechos reservados en ambas interfaces.

## Uso web

La ejecución no cambia: inicia `app.py` y abre la dirección local habitual del
servidor. La nueva hoja visual se encuentra en `static/pro-ui.css`.

## Android

El código Android se encuentra en `omr-camera` y la aplicación está identificada
como versión 2.0 (`versionCode 7`). Para generar el APK se necesita JDK 17 y el
SDK de Android configurado. Desde esa carpeta, la tarea es `gradlew.bat
:app:assembleDebug`.

> El entorno de Codex verificó el HTML, el CSS, el JavaScript y la sintaxis de
> Python. No pudo generar el APK porque la política del equipo impidió descargar
> el JDK 17 portátil y el equipo solo dispone de Java 8.
