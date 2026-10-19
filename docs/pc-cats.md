# Gatos y animaciones de PC

`data/inputs/pc_cats.json` es el catálogo curado de las 17 unidades exclusivas
PC (35 formas). Se revisaron sus tablas de stats y habilidades en The Battle
Cats Wiki el 2026-10-17; cada medición conserva su URL. No se mezclan IDs con
móvil: el ID público es `100000 + source_id`.

```bash
.venv/bin/python sync_pc_cats.py --online --dry-run
.venv/bin/python sync_pc_cats.py --online
.venv/bin/python sync_pc_cats.py --dry-run
```

`--online` descarga únicamente fuentes que faltan. El cache conservado en
`workspace/pc-sources` permite reconstruir sin red; no borrarlo para una reparación.
Los números `revision` del input son referencias del template de la wiki; no
se usan como revisiones MediaWiki fijadas. Los hashes del manifiesto identifican
los bytes realmente utilizados. Una actualización de esas fuentes requiere
conservar el cache anterior y seleccionar otro `--cache` para revisar diferencias.

El sincronizador prepara y valida todos los paquetes antes de publicar archivos.
No ofrece una transacción global frente a fallos de disco; revisar outputs si se
interrumpe la escritura. `--dry-run` no modifica outputs públicos (con `--online`
puede descargar fuentes al cache). La segunda ejecución debe dar cero cambios.

Outputs:

- `pc_cats.json`: catálogo público completo; también se incorpora como
  `pc_catalog` en `cats_data.json`, conservando `units` y metadata móviles.
- `cats_pc/<id>.zip`: archivos nativos PNG/imgcut/mamodel/maanim con rutas
  `<id>/<forma>/<id>_<forma>...`. Estados 00 caminar, 01 reposo, 02 ataque,
  03 retroceso. Se conservan todas las columnas y pistas de las fuentes.
- `cats_pc/manifest.json`: hashes, tamaños, URLs y hashes de fuentes, avisos.
  Este manifiesto tiene un ciclo independiente del manifiesto PONOS móvil.

`actualizar_cats_info.py` conserva el catálogo desde `pc_cats.json` al regenerar
las stats móviles. La app utiliza el mismo visor, caché y comprobación SHA-256,
con `cats_pc/` para IDs PC. Los archivos deben publicarse en GitHub y la app
actualizada debe compilarse antes de que sus descargas estén disponibles.

## Revisión de stats

Se contrastaron HP, ataque, rango, velocidad, retrocesos, ciclo y foreswing de
las 35 formas con las tablas de cada artículo. Cambios respecto al catálogo
anterior: ciclo de Bun Bun Monger 90 → 89 frames (tres formas) y Wise Empress
Nobel 365 → 364 (dos formas). Natsu Mikan incorpora condiciones de nivel/tesoros,
ataque de área y recarga publicada de 325 segundos. Su coste de capítulo 2 es 5.908, también verificado.
No se inventan bases para mediciones que no reproducen exactamente su referencia
con la curva de nivel compartida; por ejemplo, 38.522 de ataque de Berius y
30.000 HP de Natsu evolucionada no permiten recuperar una base entera a nivel 30.
Natsu usa los totales publicados de nivel 30 en ambas formas: 30.000 HP y
35.700 de daño. La tabla publica estos valores para las dos formas; sus cifras
iniciales de 1.500 HP y 1.600 de daño no reproducen esos totales con la curva
compartida, por lo que no se usan como base del cálculo. La app conserva las
mediciones de nivel 30 y escala otros niveles respecto a esa referencia, sin
inventar una base entera ni un reparto del daño multigolpe. El DPS de referencia
es 939,47 (35.700 / 38 segundos).

En la app, `Traited enemies` incluye los siete traits presentes en PC; `all enemies`
incluye además Traitless. No se añaden Relic/Aku, posteriores a este juego. Cats
se conserva como objetivo PvP en el texto de cada habilidad. Los objetivos son
por habilidad: la resistencia de Javelins, Cat Maid, Mimiluga, Natsu y Tenten
es solo contra Cats, aunque otras habilidades afecten a enemigos. No deben
recibir resistencia simulada contra los traits de esas otras habilidades.
Se corrige también el rango `400~3,000` de Natsu.

Los backswings PC se derivan del ataque importado cuando se conoce el último
golpe, sin sustituir los ciclos publicados por la duración de la animación.
Hay diferencias entre las tablas y las pistas (por ejemplo, Odin tiene una
animación más larga que el ciclo publicado); se conservan ambos conceptos.
Las dos formas de Kitaro terminan antes del foreswing publicado: backswing null.
Neko-Musume no declara foreswing; Natsu presenta tiempos multigolpe ambiguos:
backswing null. Odin básico tiene un estado Knockback sin pistas: se conserva
ese recurso vacío y se avisa; no se copia el de otra forma.

Para exportar solo el catálogo PC a una app, sin cambiar sus unidades móviles:

```bash
python sync_pc_cats.py --app-data ../CatStats/app/src/main/assets/data/cats_data.json --app-details ../CatStats/app/src/main/assets/data/pc_cat_details.json
```
