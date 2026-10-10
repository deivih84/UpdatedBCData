# Catálogo de unidades exclusivas de PC

La fuente curada es `data/inputs/cats_pc.json`. El JSON público conserva las
unidades móviles en `units` y añade las fichas PC incompletas en `pc_catalog`.
CatStats muestra estas fichas por rareza, con sus formas, imágenes, datos
publicados, enlace de referencia y favoritos. No participan en cálculos de
combate, recomendaciones ni rankings mientras sus estadísticas no estén
verificadas para el esquema consumidor.

## IDs y compatibilidad

La ID interna de PC es `100000 + source_id`, dentro de `[100000, 200000)`.
Odin PC #911 usa `100911`; esta clave nunca representa al gato móvil #911.
Las imágenes se publican como `images/cats/uni100911_f00.png`, etc.
La app muestra la ID original (`PC #911`) y guarda favoritos con la interna.
Las IDs no dependen del nombre ni del orden de las fichas.

`metadata.total_units` cuenta las entradas de `units`, no la ID máxima.
`mobile_units`, `pc_units` y `pc_catalog_units` explicitan los tres grupos.
`pc_source_revision` es la fecha de revisión de la fuente PC;
`metadata.version` sigue identificando los datos móviles. Una app antigua
puede ignorar `pc_catalog`; no soporta las futuras IDs verificadas dispersas.
La promoción a `verified` está bloqueada en el productor y la app: adaptar y
verificar los cálculos y tiempos PC antes de publicar/exportar ese formato.

Una respuesta remota antigua sin revisión PC conserva el catálogo PC del
asset local de la app. Una respuesta versionada con catálogo vacío permite
vaciarlo explícitamente. Un fallo de descarga/validación conserva la última
respuesta aceptada; en la primera carga usa el asset local. Las fichas PC nunca
se toman del catálogo móvil por coincidencia de nombre.

## Actualizar solo PC

Desde el Python 3.12 del venv, revisar la fuente y ejecutar:

```powershell
python update_pc_cats.py --dry-run
python update_pc_cats.py
python update_pc_cats.py --dry-run
```

La segunda comprobación debe indicar `Changed files: 0`. Este comando fusiona
solo PC y conserva los valores de todas las unidades móviles. Puede exportar
el resultado con `--app-data PATH` apuntando explícitamente al JSON de la app.
No hace pull, commit ni push. Actualiza `data_version.json` si existe junto al
JSON modificado. No debe usarse para omitir verificaciones de animaciones en
una actualización móvil.

El generador habitual `actualizar_cats_info.py` también carga esta fuente
canónica antes de escribir, de modo que un `update_all.py` no elimina PC.
No usa una copia antigua de la fuente PC en `workspace/data`.

## Revisión y datos desconocidos

La fuente tiene `schema_version: 1`, `reviewed_at` y una lista `entries`.
Cada ficha guarda `source_id`, `status`, `info` y `forms`. Los campos de
identidad, nombres, rareza, URL y formas se validan antes de la escritura.
Los datos numéricos publicados indican unidades, nivel y condiciones de
tesoros; un contexto desconocido permanece `null`. No se convierten valores
de nivel alto a estadísticas base ni se deducen multiplicadores móviles.
Los tiempos se muestran en las unidades publicadas, sin calcular un backswing.

Las habilidades se conservan descriptivamente y con su referencia. Las
habilidades que mencionan objetivos PvP y enemigos móviles no se reducen a
una bandera exclusivamente PvP; el texto conserva ambas condiciones.

- `catalog_only`: identidad y formas comprobadas, conversión CSV incompleta.
  Se publica en `pc_catalog`, sin estadísticas CSV artificiales.
- `verified`: estado reservado para una futura conversión completa. La versión
  actual lo rechaza incluso con evidencia completa: el consumidor todavía usa
  semántica móvil para tiempos y cálculos. Antes de habilitarlo, verificar cada
  columna, incluidos ceros/defaults y tiempos, y representar los tiempos
  desconocidos sin heredar backswings móviles. Tener vida, daño y alcance en la
  wiki no permite promover una ficha.

Los ZIP móviles y su manifiesto conservan sus fuentes PONOS. Sin recursos PC
verificados, los backswings PC son `null` con advertencias visibles y el visor
de animaciones permanece deshabilitado. No reutilizar `cats/911.zip` para Odin.

## Importación inicial y discrepancias previas

Se revisaron 17 fichas PC (IDs originales 901–917), con 35 formas e imágenes,
incluidos 13 Ubers y cuatro Special. Todas quedan `catalog_only` en la revisión
2026-10-09: la wiki no permite verificar todos los campos CSV y su semántica.
Las imágenes procesadas tienen 110×85 píxeles; los archivos descargados se
conservan en el inbox local ignorado, fuera de Git.

La aplicación inicial usa `update_pc_cats.py` para preservar íntegros los
gatos móviles publicados. La regeneración móvil encuentra una discrepancia
previa en 877–881: `names.txt` repite el nombre evolucionado y el generador
interpreta una tercera forma, mientras el JSON publicado declara dos.
La validación estricta contra esos inputs sigue avisando de esos cinco casos.
Este catálogo PC no inventa ni corrige formas móviles.

Los datos PC se transcriben de las páginas enlazadas de Battle Cats Wiki;
la fuente conserva atribución a sus contribuidores y licencia CC-BY-SA.
Las discrepancias internas de la wiki requieren revisión antes de promover
una ficha a cálculos de combate.
