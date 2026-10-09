# Mantenimiento automático de eventos EN

Las rutas de BCData y drawables se configuran en [workspace.md](workspace.md).
CatStats es opcional y el mismo destino configurado funciona en Windows/Linux.

```powershell
pip install -r requirements-gacha-sync.txt
python fetch_bc_events.py --dry-run
python fetch_bc_events.py
```

`fetch_bc_events.py` mantiene el catálogo, los carteles y el calendario EN sin
Discord. El workflow `update_bc_schedule.yml` lo ejecuta con `--online` cada seis
horas, junto al sincronizador de gachas. Hay que publicar estos cambios en la rama
por defecto para activar la nueva versión del workflow; no necesita tareas de ChatGPT.

## Fuentes y asociación de eventos

El calendario procede de `sale.tsv` de PONOS. Si la autenticación o descarga
falla, se usa el espejo de Godfat, validando el formato antes de cambiar archivos.
El informe registra la fuente y el hash. El dry-run usa el espejo directamente y
no modifica archivos ni credenciales. `--tsv ARCHIVO --today AAAA-MM-DD` permite
reproducir un calendario guardado.

Los IDs se resuelven con el último EN de `../BCData`, o `--bcdata RUTA`, y con
`event_name_index.json`, que permite ejecutar GitHub sin el checkout local.
`--online` intenta refrescar las referencias públicas de BCData. Si están
retrasadas o inaccesibles, conserva el índice guardado y muestra una advertencia.
Un refresco parcial conserva los nombres conocidos de recursos de login.
Los nombres de mapas y misiones no se convierten automáticamente en eventos.

Se asocian IDs y nombres/aliases exactos de `all_events.json`, sin búsquedas
aproximadas. Un conflicto conserva la entrada y su calendario anterior vigente.
Se procesan todos los IDs de una fila. Las campañas numeradas tienen identidad
propia: 120M no hereda la foto de 111M. Una campaña nueva sustituye una ocurrencia
antigua sin ID que siga solapándose en el calendario, conservando su catálogo histórico.

## Carteles y catálogo

Se consulta la API de Miraheze, con Fandom como alternativa. Solo se usa el
cartel declarado mediante `PageBanner` de la página correspondiente, prefiriendo
el archivo EN original. Se rechazan iconos, miniaturas y dimensiones inadecuadas
(mínimo 600×300, proporción entre 1,5:1 y 3:1). Una URL con sección necesita un
cartel explícito para no tomar por error la foto general de otra celebración.

Un evento nuevo se añade cuando tiene nombre del juego y cartel verificable.
Los eventos registrados conservan su foto y descripción si la descarga falla.
Las descripciones existentes se respetan; las nuevas pueden recibir un extracto
breve de la wiki con su URL. Las fotos faltantes o pequeñas de eventos antiguos
también se intentan reparar. `--skip-images` actualiza solo asociaciones y fechas
reconocidas, sin dar de alta eventos que todavía carezcan de cartel.

Las imágenes usan `images/events/event_NOMBRE_HASH.png`: el hash cambia la URL
cuando cambia el cartel. Se copian también al drawable de CatStats si existe;
`--app-drawables RUTA` permite otro destino. Se conservan los recursos anteriores.

## Informes y excepciones

- `all_events.json`: catálogo compatible con la app, con IDs y aliases.
- `event_name_index.json`: nombres conocidos de recursos EN.
- `event_sync_state.json`: procedencia y hashes de carteles y descripciones automáticas.
- `event_sync_report.json`: pendientes, fotos que faltan y últimos cambios aplicados.
- `.event_sync_run.json`: resultado de esta ejecución, ignorado por Git y guardado
  como artifact de GitHub Actions. El resumen también aparece en Actions.

`unknown_identity` indica que el índice aún no conoce el ID. `identity_conflict`
requiere verificar qué entrada corresponde. `image_not_found` y
`image_unavailable` se reintentan en cada ejecución; no se reemplazan por fotos
parecidas. Algunos eventos no tienen un cartel completo publicado: esos casos
pueden necesitar una asociación verificada una sola vez.

Para resolver una excepción, registra `event_id` o `event_ids` en su entrada y
los aliases comprobados. `event_sync_config.json` admite `wikiPages` (nombre
canónico → página exacta) y `bannerFiles` (nombre → archivo verificado de esa
wiki). `imageOverrides` fija un archivo existente de `images/events/` por nombre
canónico: tiene prioridad sobre la wiki, conserva sus bytes y también lo copia
al drawable. Los siete eventos de enemigos Colossal conservan sus carteles
originales (por ejemplo, Baron Seal usa `event_seal.png`). Si el archivo elegido
falta o es inválido, queda pendiente sin sustituirlo por otro cartel.
No asocies fotos únicamente por las dimensiones ni encabezados genéricos.

La publicación tiene reemplazos atómicos y rollback de escrituras fallidas.
Un calendario vacío/inválido detiene la actualización, conservando los datos.
La sección `gachas` se mantiene. El flujo anterior que consulta Discord continúa
disponible con `python fetch_bc_events.py --legacy-discord`.

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python update_cat_animations.py --dry-run
```
