# Mantenimiento automático de banners EN

```powershell
pip install -r requirements-gacha-sync.txt
python sync_gacha_catalog.py --dry-run
python sync_gacha_catalog.py
python fetch_bc_schedule.py
```

La configuración común se describe en [workspace.md](workspace.md). El script
usa el BCData configurado, o el último EN de `../BCData` cuando está disponible.
`--bcdata RUTA` permite indicarlo explícitamente. En GitHub, `--online` obtiene
los pools de Godfat y comprueba que la página corresponde al evento solicitado,
que las listas están completas y que las probabilidades coinciden con PONOS.
El espejo público original de BCData está retrasado respecto al checkout local;
por eso no se utiliza como fuente de pools actuales en el workflow.

`--tsv ARCHIVO --today AAAA-MM-DD` reproduce un calendario guardado.
`--skip-images` permite actualizar únicamente las identidades ya reconocidas y
sus pools. `--dry-run` no modifica catálogo, imágenes, informes ni credenciales.
Su calendario procede del espejo de Godfat; las ejecuciones que aplican cambios
intentan obtener el calendario de PONOS usando la autenticación existente.
Si falla, usan el espejo validado de Godfat y registran la procedencia.

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

Las imágenes se buscan por ID exacto del banner e imgID en las APIs de
Miraheze/Fandom, exigiendo el archivo EN; una imagen de otro
banner no se elige por parecido del título.
Los archivos sin idioma no sirven como alternativa automática para EN: pueden
ser japoneses. Solo se admiten los originales 174 (Platinum), 640 (Legend) y
582 (Dynastyfest), revisados visualmente como ingleses. Los carteles de eventos
siguen la misma regla: un original sin idioma exige una selección explícita en
`bannerFiles` de `event_sync_config.json`.
Si esos archivos no existen, `seriesBannerIds` permite asociar explícitamente
una serie con un banner completo de la wiki verificado previamente. Las series
21 (Platinum), 46 (Legend) y 47 (Dynastyfest) usan los banners de sus páginas
principales cuando falta la imagen del ID nuevo. Estos banners de familia no
afirman representar las unidades del pool actual; las unidades se actualizan
desde los datos del juego por separado.
Los archivos `Gatya btn...` son botones del menú y no se seleccionan. Se exigen
dimensiones de al menos 600×150 y una proporción horizontal entre 2:1 y 6:1,
tanto en los metadatos de la wiki como al decodificar la descarga. Una imagen
pequeña se descarta y se continúa con el siguiente candidato.
Las altas exigen un nombre independiente del anuncio: página oficial o un único
evento de la wiki que use la imagen encontrada. Las cápsulas N/E que incluyen
objetos y otras rarezas quedan fuera del sincronizador de gachas raros R.

## Cápsulas de evento y nombres compartidos

El lector del calendario distingue los IDs por tipo: 0=N (normal), 4=E (evento),
otros=R (raros). Los IDs numéricos de `gacha_id_cache.json` pertenecen solamente
a R. Para un evento con gatos, registra `gacha_type: 4` y `gacha_id` en su entrada
de `all_gachas_en.json`; no pongas su ID en el cache de R.

`Limited Capsules` es un encabezado compartido y no se acepta como alias de una
familia. Un ID desconocido con ese texto queda sin resolver. Los anuncios de N
que mencionan expresamente Catseyes o Catfruit conservan sus nombres de cápsulas
de objetos, en vez de identificarse como Summer Break.
El calendario EN excluye Cats Eye Capsules, Special Capsules y Catfruit Capsules, tanto temporales
como permanentes. El filtro usa el nombre resuelto completo; no oculta Uberfest,
Epicfest o Superfest por contener «Special Capsules» en su anuncio. Los eventos
Cats Eye Cave y Cats Eye Caverns conservan su calendario.

En EN 15.6, E51 es Summer Break Cats Paradise (gatos 342, 375, 822, 870) y E55 es
Download Celebration! (gatos 504, 726, 776), según `GatyaDataSetE1.csv`. Sus
identidades y banners se comprobaron en las páginas de
[Summer Break Cats Paradise](https://battlecats.miraheze.org/wiki/Summer_Break_Cats_Paradise_(Event_Gacha))
y [Download Celebration!](https://battlecats.miraheze.org/wiki/Download_Celebration!_(Event_Gacha)).
Download Celebration! usa Legendary Starshines; Download Anniversary Gacha es
el banner R de héroes Uber y conserva su identidad independiente. Si cambia el
ID o contenido de un evento E, debe verificarse con sus archivos E y su página;
el sincronizador de pools R no modifica estas entradas.

Un error de descarga de pools o de validación detiene la publicación del catálogo.
Un error de imagen queda pendiente y permite aplicar los pools validados.
La publicación usa reemplazos atómicos y rollback si falla una escritura.
Las comprobaciones de animaciones del repositorio siguen siendo obligatorias
en las actualizaciones generales del juego; este sincronizador no cambia
`cats_data.json` ni la versión del juego.

## Ejecución periódica

`.github/workflows/update_bc_schedule.yml` ejecuta sincronizador, calendario y
suite de pruebas cada seis horas. También mantiene los eventos, sus carteles y
el calendario; ver [event-sync.md](event-sync.md). Publica solo los archivos públicos; la cuenta
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

JP utiliza el mismo motor con `--region jp`, datos separados y carteles propios.
Ver [gacha-sync-jp.md](gacha-sync-jp.md).
