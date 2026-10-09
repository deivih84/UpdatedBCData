# Backswing remoto de gatos

Cada unidad de `cats_data.json` publica `backswing`: una lista de frames en
el mismo orden que `stats` (primera, evolucionada, verdadera, ultra).
Por ejemplo, el ID `877` publica `[55,150]`. El juego usa 30 frames por segundo.
Un `null` significa que la fuente no permite obtener un valor; no se inventa
una animación ni se copia una forma distinta.

`update_cat_backswings.py` lee las animaciones de ataque `02.maanim` de los ZIP
incrementales ya fusionados en `cats/`. El cálculo incluye el frame cero y
las repeticiones finitas de cada pista. Al tiempo de animación se le resta
el frame del último golpe, usando las columnas CSV 62, 61 o 13.
La implementación de las repeticiones se contrasta con
[BCU Part](https://raw.githubusercontent.com/battlecatsultimate/BCU_java_util_common/master/util/anim/Part.java)
y [MaAnim](https://raw.githubusercontent.com/battlecatsultimate/BCU_java_util_common/master/util/anim/MaAnim.java).

El script exige que `cats/manifest.json.latestSource.gameVersion` coincida con
`cats_data.json.metadata.version`. Las formas ausentes y los ataques estáticos
de Iron Wall Cat y del registro no utilizado Cheetah Cat quedan como `null`,
con advertencias visibles. En 15.7.1 hay 2.123 valores disponibles y 56 formas
sin un valor calculable, sobre 2.179 formas de 882 unidades.

## Ejecución

```powershell
python update_cat_animations.py
python update_cat_backswings.py --dry-run
python update_cat_backswings.py --app-data ../CatStats/app/src/main/assets/data/cats_data.json
python update_cat_animations.py --dry-run
python update_cat_backswings.py --dry-run
python -m unittest discover -s tests -p "test_*.py" -v
```

`--app-data` es opcional y copia el JSON público final byte a byte al asset
de la app. Una ejecución sin cambios conserva los timestamps y el contenido.

El orquestador versionado en la raíz del repositorio, `update_all.py`,
ejecuta `backswings` después de `animations`. `--only animations` incluye
también ese paso dependiente; `--only backswings` permite recalcular sin
regenerar otros datos. `--export-app` copia al checkout configurado tras el
éxito del pipeline. El generador `scripts/data/actualizar_cats_info.py` incluye el campo;
si todavía no se han sincronizado las animaciones de la versión nueva, deja
valores provisionales `null` que el paso final recalcula.

## CatStats

La app deserializa el campo opcional y pasa a cada forma su valor. El valor
remoto tiene prioridad, incluyendo cero. Si falta o es negativo, usa el valor
del JSON incluido en la app y, finalmente, el archivo histórico
`backswings.txt`. Los valores quedan asociados a cada objeto `Cat`, por lo que
una recarga remota no reutiliza los valores de otra respuesta.

El intervalo completo es `último golpe + max(2 * intervalo CSV - 1, backswing)`,
coincidiendo con
[BCU DefaultData.getItv](https://raw.githubusercontent.com/battlecatsultimate/BCU_java_util_common/master/battle/data/DefaultData.java).
Esto conserva los tiempos anteriores cuando el intervalo ya cubría la
animación y corrige las formas que podían repetir antes de terminarla.
El diálogo muestra el backswing real, el último golpe para ataques múltiples
y la espera adicional cuando existe.
Los talentos de frecuencia reducen la espera, sin acortar la animación,
tanto en el detalle como en los rankings. El auditor de cobertura acepta los
valores publicados por ID antes de recurrir al TXT histórico. `names.txt`
se alinea con los nombres ya publicados para que regenerar no revierta
la localización.

El validador general conserva una discrepancia anterior en 877–881: los CSV
JP y los nombres declaran tres filas (las dos últimas idénticas), pero el JSON
actual publica dos formas y los paquetes solo suministran `f`/`c`. Este cambio
conserva exactamente las filas de `stats` publicadas; la discrepancia no se
oculta ni se fabrican terceras animaciones para hacer pasar la validación.

Las apps publicadas antes de este cambio ignoran el campo nuevo; necesitan
una actualización de la app para empezar a usar sus valores remotos.

## Valores revisados de 15.7

| ID | Unidad | Backswing por forma (frames) |
|---|---|---|
| 876 | Espíritu de Mitsuhide | 45 |
| 877 | White Rabbit of Inaba | 55 / 150 |
| 878 | Anji Yukyuzan | 95 / 95 |
| 879 | Sojiro Seta | 71 / 71 |
| 880 | Makoto Shishio | 42 / 42 |
| 881 | Seijuro Hiko | 71 / 71 |

Las nuevas formas de 401, 746 y 754 tienen 32, 235 y 136 frames,
respectivamente. Sus valores proceden de las animaciones JP 15.7.1 locales.
