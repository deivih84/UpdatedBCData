# Sincronización automática del catálogo EN

El usuario aprobó automatizar la identificación, los pools, las altas y las
imágenes de banners, aprovechando la tarea periódica existente. La ejecución
se realiza en esta sesión y mantiene los formatos que consume CatStats.

## Fuentes e identidad

El calendario oficial de PONOS proporciona IDs, fechas, textos y probabilidades.
El checkout local actualizado de BCData proporciona `GatyaDataSetR1.csv`, `unitbuy.csv` y
`GatyaData_Option_SetR.tsv` de la última versión EN declarada en `latest.txt`.
Cada pool se divide por la rareza de `unitbuy.csv`, columna 13. Se conservan
el orden y las repeticiones: las repeticiones pueden representar pesos reales.
Se rechazan filas incompletas, IDs desconocidos y probabilidades incompatibles.
En GitHub, el espejo público de BCData está retrasado y se usa el proveedor
Godfat existente, validando el ID seleccionado, todas las listas y las
probabilidades contra PONOS. No se cambia la versión de los datos de unidades
ni las animaciones.

Las asociaciones por ID existentes, aliases exactos y series configuradas
son la única base para actualizar una entrada conocida. La configuración
inicial documenta series 1 (Dynamites), 47 (Dynastyfest) y 70 (aniversarios de
descargas). Un conflicto entre estas fuentes se informa y no se aplica.
Para las altas, el nombre debe proceder de una página oficial o de un único
evento de la wiki que use una imagen identificada por el ID. Un anuncio de
PONOS por sí solo no justifica inventar un nombre canónico.

## Variantes y fechas

Se consideran banners activos, futuros hasta 180 días y cápsulas permanentes.
Dos IDs asociados a la misma familia con pools/probabilidades distintos se
guardan por separado mientras convivan en el calendario. La versión activa
se mantiene en la entrada canónica; las otras usan `<nombre> (EN #<ID>)`.
El estado conserva snapshots por evento y los metadatos de variantes, sin
modificar el formato del catálogo ni renombrar automáticamente las familias.
Las futuras Platinum/Legend conservan su fecha real: nunca reemplazan el pool
activo por haberse tratado como permanentes.

## Imágenes y publicación

Se intenta primero la página oficial y después las APIs de MediaWiki
(Miraheze, con User-Agent de contacto, y Fandom). Se buscan únicamente nombres
deterministas `Gatya bnr<ID> en.png` y `Gatya bnr<ID>.png`, el imgID declarado en opciones y
`Gatya btn<seriesID>.png`. Se valida la decodificación y dimensiones con Pillow.
Las imágenes se guardan en `images/gacha/` con nombre basado en SHA-256 para
evitar URLs obsoletas en cachés. Las imágenes descargadas se copian también al
drawable local si ese directorio existe; GitHub no requiere el checkout Android.
Se conservan las imágenes previas cuando la fuente no está disponible.
El informe incluye imágenes locales ausentes para todo el catálogo, aunque
el banner esté inactivo. Las asociaciones históricas registradas permiten
reparar imágenes de esos banners.

El plan se calcula sin mutaciones y se publica mediante archivos temporales,
reemplazos atómicos y rollback en caso de fallo. `--dry-run` no escribe nada.
Una segunda ejecución con las mismas fuentes no genera cambios de datos.
El informe JSON es estable e incluye cambios, pendientes, errores y fuentes;
GitHub muestra además un resumen legible y conserva el informe como artifact.
Un error de datos/pools detiene la publicación; una imagen o identidad dudosa
conserva lo anterior y aparece como pendiente.

## Programación y verificación

La tarea existente ejecuta sincronizador, calendario y tests antes del commit.
No publica ni persiste credenciales de `.bc_state.json` en GitHub; el archivo
se conserva localmente e ignora por Git. El workflow prepara la automatización, pero no se
activa en GitHub hasta publicar los cambios en la rama por defecto.
La CLI admite fuentes locales para reproducir y probar sin red.
Pruebas de identidad, variantes, fechas, fallos de red, entradas malformadas,
imágenes, dry-run, rollback e idempotencia. Antes de terminar se ejecutan la
suite completa, una sincronización real y un segundo dry-run sin cambios,
y la comprobación obligatoria de animaciones.
