# Mantenimiento automático de gachas JP

```powershell
pip install -r requirements-gacha-sync.txt
python sync_gacha_catalog.py --region jp --dry-run
python sync_gacha_catalog.py --region jp
python fetch_bc_schedule.py --region jp
```

El mismo motor mantiene EN y JP con catálogos, IDs y snapshots separados.
`--region en` sigue siendo el valor por defecto y conserva los nombres de
archivos existentes. La app ya solicita `all_gachas_jp.json` y el calendario JP.

## Fuentes y archivos

- `all_gachas_jp.json`: nombres, aliases, probabilidades, unidades y fotos JP.
- `gacha_id_cache_jp.json`: ID de pool raro JP → nombre canónico.
- `gacha_sync_config_jp.json`: asociaciones verificadas de series y nombres.
- `gacha_sync_state_jp.json`: pools, variantes y procedencia JP.
- `gacha_sync_report_jp.json`: pendientes y últimos cambios aplicados.
- `.gacha_sync_run_jp.json`: informe privado ignorado por Git y artifact de Actions.
- `images/gacha/banner_jp_ID_HASH.png`: imágenes con nombres distintos de EN.
- `gachas_eventos_actualizados_jp1.json`: calendario de gachas; preserva sus eventos.

PONOS JP es la fuente del calendario; Godfat JP es la alternativa validada.
El dry-run usa el espejo sin crear/refrescar credenciales. Localmente se carga
la versión JP declarada en `../BCData/latest.txt`; se puede indicar otra copia
con `--bcdata RUTA`. `--online` obtiene los pools de Godfat comprobando tanto el
selector de idioma JP como el evento exacto, sus unidades y las probabilidades
de PONOS. No utiliza el cache ni los pools EN.

Godfat no publica las ofertas antiguas de primera compra, tipos 2/3. Para
ellas se conserva el snapshot JP previamente verificado, comprobando que sus
probabilidades siguen coincidiendo con el calendario. El informe las marca
`starter_pool_not_available_online`: no afirma haber refrescado esas unidades.
Si no existe snapshot, quedan pendientes. Un error en un pool normal sigue
deteniendo la publicación; nunca se acepta el pool de otro evento o idioma.

## Nombres, variantes e imágenes

Los anuncios JP son frecuentemente frases promocionales compartidas entre
banners. No se usan para identificar familias ni se guardan como aliases.
Se resuelve por ID JP, serie verificada o nombre independiente de la página
oficial/wiki. Los nombres canónicos se mantienen en inglés cuando existe una
equivalencia verificada. Los nombres japoneses conservan claves Unicode
distintas; un nombre nuevo sin equivalencia puede permanecer en japonés.

Las ofertas de primera compra (tipos 2/3) no se presentan como campañas
públicas permanentes en el calendario JP. Sus snapshots se conservan en el catálogo.

Las variantes usan `(JP #ID)`. El calendario solo publica nombres reconocidos
por el catálogo regional. N/E conservan su espacio de IDs por tipo y quedan
fuera del sincronizador de pools R, igual que en EN.

Se prefieren archivos `ja`/`jp` y los originales japoneses sin sufijo de la wiki;
no se solicita automáticamente el archivo con sufijo `en`. Se exigen carteles
completos y se rechazan botones, miniaturas y retratos cuadrados. Las imágenes
se copian al repositorio y al drawable local de CatStats si existe.

`seriesBannerIds` permite carteles de familia comprobados cuando falta el ID
actual. Platinum utiliza su archivo japonés `Gatya bnr174 ja.png`. Legend usa
por ahora el cartel completo compartido de su página (`Gatya bnr640.png`, con
texto en inglés); esa imagen de familia no describe el contenido actual del
pool. Las unidades y probabilidades siempre proceden de JP por separado.
Nekoluga utiliza el cartel japonés verificado de familia #962 si falta el actual.
Una imagen no disponible queda pendiente y conserva la anterior.

`--tsv ARCHIVO --today AAAA-MM-DD` reproduce una ejecución guardada.
`--skip-images` actualiza pools conocidos sin buscar fotos/nombres.
`fetch_bc_schedule.py --region jp --dry-run` previsualiza el calendario sin escribir.

## Ejecución periódica

El workflow existente ejecuta también el catálogo y calendario JP cada seis
horas, comprueba los tests y publica los archivos públicos de ambas regiones.
Para activarlo hay que publicar estos cambios en la rama por defecto. Las
credenciales y los informes privados de ejecución no se incluyen en commits.

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python update_cat_animations.py --dry-run
```
