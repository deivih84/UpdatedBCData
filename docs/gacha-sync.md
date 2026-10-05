# Mantenimiento automático de banners EN

```powershell
pip install -r requirements-gacha-sync.txt
python sync_gacha_catalog.py --dry-run
python sync_gacha_catalog.py
python fetch_bc_schedule.py
```

El script usa el último EN de `../BCData` cuando ese checkout está disponible.
`--bcdata RUTA` permite indicarlo explícitamente. En GitHub, `--online` obtiene
los pools de Godfat y comprueba que la página corresponde al evento solicitado,
que las listas están completas y que las probabilidades coinciden con PONOS.
El espejo público original de BCData está retrasado respecto al checkout local;
por eso no se utiliza como fuente de pools actuales en el workflow.

`--tsv ARCHIVO --today AAAA-MM-DD` reproduce un calendario guardado.
`--skip-images` permite actualizar únicamente las identidades ya reconocidas y
sus pools. `--dry-run` no modifica catálogo, imágenes, informes ni credenciales.
Su calendario procede del espejo de Godfat; las ejecuciones que aplican cambios
obtienen el calendario directamente de PONOS usando la autenticación existente.

## Qué se mantiene

- `all_gachas_en.json`: nombres, aliases, unidades, probabilidades e imágenes.
- `gacha_id_cache.json`: asociación precisa entre ID de pool EN y nombre.
- `gacha_sync_state.json`: snapshots de pools, variantes, series y procedencia.
- `gacha_sync_report.json`: pendientes y últimos cambios aplicados.
- `.gacha_sync_run.json`: informe de la ejecución, ignorado por Git.
- `images/gacha/banner_en_ID_HASH.png`: imágenes verificadas, con URL distinta
  cuando cambia el contenido para evitar que las apps conserven la foto antigua.

El nombre conocido se conserva para la versión activa. Si el calendario contiene
otra versión con unidades o probabilidades distintas, aparece como
`The Dynamites (EN #1068)`, por ejemplo. Cuando esa versión pasa a estar activa,
su pool pasa al nombre canónico. La entrada anterior de variante se conserva
para no romper referencias de clientes. No se asignan pools por coincidencias
aproximadas de texto.

El script copia las imágenes nuevas al drawable configurado si existe en el PC.
Puede indicarse otro destino con `--app-drawables RUTA`. GitHub solamente necesita
este repositorio. Los recursos usados por clientes anteriores se conservan.

## Casos pendientes

`unknown_identity` significa que falta una asociación fiable. `identity_conflict`
significa que ID, serie o alias identifican familias diferentes. `image_not_found`
o `image_unavailable` conserva la foto anterior. `missingImages` enumera archivos
locales que faltan para cualquier banner, también los inactivos.

Para resolver una identidad, añade el ID a `gacha_id_cache.json`, o una serie a
`seriesNames` en `gacha_sync_config.json`, tras comprobar la asociación. Para
equivalencias de nombres canónicos de la wiki usa `wikiNames`. Los IDs de serie
proceden de `GatyaData_Option_SetR.tsv`, no del número de pool. El siguiente run
actualiza los datos sin volver a preguntar.

Las imágenes se buscan por ID exacto del banner, imgID y serie en las APIs de
Miraheze/Fandom, prefiriendo el archivo EN cuando existe; una imagen de otro
banner no se elige por parecido del título.
Las altas exigen un nombre independiente del anuncio: página oficial o un único
evento de la wiki que use la imagen encontrada. Las cápsulas N/E que incluyen
objetos y otras rarezas quedan fuera del sincronizador de gachas raros R.

Un error de descarga de pools o de validación detiene la publicación del catálogo.
Un error de imagen queda pendiente y permite aplicar los pools validados.
La publicación usa reemplazos atómicos y rollback si falla una escritura.
Las comprobaciones de animaciones del repositorio siguen siendo obligatorias
en las actualizaciones generales del juego; este sincronizador no cambia
`cats_data.json` ni la versión del juego.

## Ejecución periódica

`.github/workflows/update_bc_schedule.yml` ejecuta sincronizador, calendario y
suite de pruebas cada seis horas. Publica solo los archivos públicos; la cuenta
y el JWT de `.bc_state.json` no se añaden al commit. Cada ejecución conserva el
informe como artifact y presenta el resumen en GitHub Actions.
El archivo de autenticación estaba registrado en Git pese al ignore; esta
actualización lo retira del seguimiento conservando la copia local.

Las regresiones de pools históricos usan muestras congeladas en
`tests/fixtures/gacha_pools_2026_08.json` y pasan por el parser real del proveedor.
El catálogo vivo se valida por estructura, rarezas, probabilidades y aliases;
añadir una unidad válida no debe romper una prueba que describía una versión antigua.

Los cambios locales del workflow deben publicarse en la rama por defecto para
activar esta versión de la automatización. También se puede ejecutar manualmente
desde la pestaña Actions después de publicarlo. Ninguna tarea de ChatGPT es necesaria.
