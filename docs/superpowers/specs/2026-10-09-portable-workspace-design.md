# Espacio de trabajo portable de UpdatedBCData

Estado: diseño aprobado e implementado. Validación y límites de plataforma en
`docs/portability-validation.md`.

## Objetivo

Un clon de UpdatedBCData debe contener los generadores, utilidades y datos
auxiliares necesarios para mantener el proyecto desde Windows o Linux. Un
agente de IA debe poder descubrir qué ejecutar, configurar sus fuentes y
verificar el resultado sin depender de rutas del ordenador original.

La reproducción tiene dos niveles: los calendarios y catálogos funcionan con
fuentes online; la regeneración completa de datos y animaciones necesita las
extracciones y paquetes de juego de BCData. Estos paquetes no se pueden
reconstruir únicamente a partir de los JSON publicados.

## Hallazgos del inventario

Revisión realizada el 9 de octubre de 2026. El árbol Git estaba limpio antes
de crear este documento. La suite existente ejecutó 140 tests correctamente.

| Ubicación actual | Contenido o problema | Tratamiento propuesto |
|---|---|---|
| Raíz de UpdatedBCData | Sin README de instalación; scripts modernos y datos públicos juntos | Mantener interfaces públicas y añadir guía de entrada |
| `gacha_sync_config.json`, `gacha_sync_config_jp.json`, `event_sync_config.json` | `appDrawables` contiene la ruta absoluta del usuario original | Configuración portable y override local común |
| Carpeta externa `Downloads/A/Automatizacion` | Orquestador, 12 generadores/utilidades y dos tests | Incorporar fuentes y tests al repositorio |
| Subcarpeta externa `Automatizacion/images` | Dos utilidades Python y seis PNG | Incorporar utilidades; inventariar los PNG antes de decidir su destino |
| Subcarpeta externa `Automatizacion/Pruebas gatchas` | Mapeador manual, `names.txt`, `gatchas.txt` | Conservar como herramientas históricas documentadas |
| `CatStats/scripts` | Generación de enemigos, stages y resúmenes fuera del repo | Incorporar generadores y dependencias directas |
| `CatStats/app/src/main/assets/data` | Nombres, combos, backswings, CSV de talentos y otros inputs | Incorporar los inputs realmente utilizados y registrar procedencia |
| `../BCData` | Fuentes de juego, extracciones y paquetes incrementales | Dependencia de datos explícita y configurable |
| `AGENTS.md` | Rutas personales y referencias a scripts ausentes | Reescribir como contrato operativo para agentes |
| `CLAUDE.md` | Instrucciones antiguas; afirma que no existen tests | Remitir a AGENTS.md como fuente única |
| `.gitignore` | Excluye los dos bots locales y no cubre un workspace nuevo | Separar credenciales y temporales de código versionable |
| Planes y specs antiguos | Ejemplos con rutas personales e instrucciones externas | Identificarlos como históricos; dirigir al procedimiento vigente |

El alcance externo revisado son las carpetas identificadas por las referencias
del propio proyecto. No se ha realizado una búsqueda indiscriminada en todo el
ordenador.

### Fuentes que se incorporarán

De Automatizacion: `update_all.py`, `actualizar_cats_info.py`,
`actualizar_combo_data.py`, `actualizar_descripciones.py`,
`actualizar_descripciones_enemigos.py`, `actualizar_enemies.py`,
`actualizar_evolution_costs.py`, `actualizar_imagenes.py`,
`actualizar_names.py`, `actualizar_names_enemigos.py`,
`actualizar_talentos.py`, `backswings.py`, `enemy_backswings.py`,
`test_actualizar_cats_info.py` y `test_update_all.py`.

De CatStats: `build_enemies_json.py`, `parse_stages.py`,
`build_update_summary.py`, `update_summary_core.py`,
`update_summary_agent_prompt.md`, `validate_cats_data.py`, y los tests
pertinentes de esas herramientas. Los auxiliares de medallas y animaciones se
clasificarán por su uso actual; la sincronización incremental existente será
el flujo oficial de animaciones.

Las copias externas originales se conservan durante la migración. El nuevo
repositorio será el origen oficial de las herramientas incorporadas; se
documentará cómo abandonar los comandos antiguos.

## Organización elegida

```text
UpdatedBCData/
  README.md                    # Instalación y comandos de entrada
  AGENTS.md                    # Contrato operativo breve para IA
  CLAUDE.md                    # Referencia a AGENTS.md
  workspace_paths.py           # Resolución común de configuración y rutas
  workspace.example.json       # Ejemplo portable, versionado
  workspace.local.json         # Ajustes de cada ordenador, ignorado
  requirements.txt             # Dependencias del mantenimiento completo
  requirements-gacha-sync.txt  # Interfaz existente para el workflow online
  update_all.py                # Entrada compatible del pipeline incorporado
  scripts/
    data/                      # Generadores importados
    tools/                     # Utilidades puntuales con CLI explícita
    legacy/                    # Herramientas manuales e históricas
  data/
    inputs/                    # Inputs y excepciones necesarios, versionados
  workspace/                   # Extracciones, entradas nuevas y temporales
  docs/
    workspace.md               # Configuración y reproducción Windows/Linux
    architecture.md            # Mapa de entradas, outputs y dependencias
    migration-inventory.md     # Procedencia de archivos incorporados
  tests/
  .github/workflows/
  ...                          # Scripts y datos públicos existentes
```

Se mantienen los scripts actuales de la raíz para conservar los comandos del
workflow y los imports de los tests. Se mantienen los nombres y ubicaciones
de JSON públicos, `images/`, `cats/` y `update_summaries/` para conservar sus
URLs. No se trasladará la app Android completa ni todo el repositorio BCData
a este repositorio de datos.

## Contrato de rutas

La raíz se calcula a partir de la ubicación del código, nunca del directorio
desde el que se ejecuta Python. Se usa `pathlib` y se pasan argumentos a los
subprocesos como listas, sin comandos dependientes de una shell.

Precedencia: argumento CLI explícito, variable de entorno documentada,
`workspace.local.json`, y valor por defecto portable. Las rutas relativas de
configuración se resuelven respecto a la raíz del repositorio. Un override
explícito inválido produce error; no se sustituye silenciosamente.

BCData puede estar en `workspace/BCData`, en `../BCData` o en otra ruta
configurada. La app se configura mediante una única ruta `catstats`; de ella
se derivan assets y drawables. La app es opcional. Los argumentos existentes
`--bcdata`, `--drawables`, `--repo` y equivalentes se conservan y tienen
prioridad. La copia de imágenes configurada debe funcionar tanto en Windows
como en Linux, eliminando el requisito actual `os.name == 'nt'`.

Los JSON de configuración compartidos no contienen rutas de una persona.
Los calendarios online no requieren BCData ni CatStats. La CLI describe las
fuentes necesarias para cada comando y las rutas efectivas.

## Inputs y salidas independientes de CatStats

Se inventarían las lecturas de cada generador. Se incorporan los inputs
necesarios de assets: nombres, estado inicial de combos, filas protegidas de
talentos, niveles de talentos, backswings y referencias de nombres y
descripciones que no puedan generarse en el propio paso. No se copian assets
ajenos al pipeline por su mera presencia en la carpeta.

Los inputs curados y acumulativos se versionan en `data/inputs`; los
intermedios reproducibles se escriben en `workspace`. Se documenta qué
archivos son mantenidos, generados o semillas iniciales. Una copia Git nueva
debe preservar las excepciones de talentos 105, 107, 258, 259 y 261, el
historial de combos y los metadatos existentes de unidades.

Los outputs finales se escriben primero en UpdatedBCData. La exportación a
CatStats es explícita o depende de una ruta configurada y documentada. Se
verifican archivos y directorios necesarios antes de comenzar a generar.
No se inicia la app ni se ejecuta una compilación Android para actualizar
datos.

## Orquestador y utilidades

Se conserva el orden names, combos, talents, enemies_csv, enemies_json,
stages, cats_info, evolution y animations. Las versiones se seleccionan
semánticamente por región; el diseño no fuerza que EN y JP tengan la misma
versión. Los argumentos se validan con argparse; un nombre de paso inválido
no puede resultar en una ejecución vacía considerada exitosa.

Un fallo detiene los pasos dependientes y devuelve código no cero. No se
publica una nueva versión de datos ni se ejecuta un push tras un fallo.
`--only animations` conserva la idempotencia existente. La compatibilidad
de `--skip-pull` se documenta: el código externo actual no define ningún
paso pull, aunque anuncia esa opción.

Los resúmenes se generan con versiones explícitas por región. Se incorporan
las herramientas necesarias para ese paso y se conserva su protocolo de
borrador/validación. Si se conserva `--push`, solo publica archivos de salida
identificados por el pipeline, nunca un `git add .` de todo el workspace.

Las herramientas que actualmente modifican `./` al importarlas deben tener
un `main` y una CLI con origen/destino explícitos. El procesamiento de
imágenes conserva los originales por defecto y escribe al repositorio
público; también copia a drawables cuando esté configurado. El inventario
registra las herramientas históricas para que una IA no las confunda con el
flujo oficial de gacha.

## Instalación y documentación

Python 3.12 es la versión inicial de validación, coherente con el workflow
actual. La instalación usa un entorno virtual local y ficheros de
requirements compartidos. Se añaden las dependencias realmente utilizadas
por los scripts incorporados, como pandas y cloudscraper, y se verifica su
instalación. Los bots Discord quedan como uso opcional separado y se revisan
por credenciales incrustadas antes de incorporarlos a Git.

README proporciona pasos concretos para PowerShell y shell Linux, instalación
de dependencias, tests, configuración de BCData y exportación opcional. La
guía explica cómo obtener/conservar paquetes fuente y qué queda fuera de
Git; no promete regenerar animaciones sin esos paquetes.

AGENTS.md contiene mapa de tareas, fuentes de verdad, comandos seguros de
inspección y validación, separación EN/JP, archivos que no se deben stagear y
el contrato obligatorio de animaciones. La arquitectura detallada queda en
docs para evitar contexto inicial duplicado. Se conserva la documentación
histórica con una advertencia visible y enlaces a instrucciones actuales.

`.gitignore` cubre entornos virtuales, configuración local, credenciales,
fuentes descargadas y temporales. Las imágenes y ZIPs públicos necesarios
siguen versionados. Se clasifica el APK ya versionado sin eliminarlo como
parte incidental de la reorganización.

## Verificación y criterios de aceptación

1. No hay rutas personales de producción en código o configuración compartida.
   Las únicas referencias históricas se identifican como tales.
2. Una copia limpia de los archivos versionados instala dependencias y pasa
   todos los tests sin acceso a las carpetas personales actuales.
3. Los entrypoints funcionan desde otro directorio y desde rutas con espacios.
   Importar generadores no requiere extraer datos ni modifica archivos.
4. Tests nuevos cubren precedencia de rutas, overrides inválidos, ausencia de
   CatStats, selección semántica EN/JP, propagación de configuración a procesos,
   errores del pipeline y preservación de inputs personalizados.
5. CLI y diagnósticos informan qué fuentes faltan antes de escribir outputs.
   Los tests no contactan PONOS ni publican cambios.
6. Se añade CI de validación con Windows y Ubuntu, Python 3.12. La validación
   local en Windows se distingue de la ejecución Linux todavía no observada.
7. Se ejecuta `python -m unittest discover -s tests -p "test_*.py" -v`.
8. Se ejecuta `python update_cat_animations.py --dry-run` con las fuentes locales
   disponibles, conservando los avisos declarados. Una comprobación final tras
   cualquier cambio de animaciones debe mostrar cero cambios pendientes.
9. Se revisa el diff para evitar cambios de datos públicos causados únicamente
   por esta migración. No se ejecuta automáticamente una actualización online,
   una extracción completa, un commit o un push para probar portabilidad.

## Secuencia de implementación prevista

1. Configuración común, diagnóstico y pruebas de portabilidad de rutas.
2. Incorporación de generadores, inputs y tests; independencia de CatStats.
3. Incorporación del orquestador y utilidades con validación de errores.
4. Integración de las rutas comunes con los sincronizadores existentes.
5. Instalación reproducible, documentación para IA, inventario y CI.
6. Validación en copia limpia, suite completa, dry-run y revisión del diff.

El plan de implementación está en
`docs/superpowers/plans/2026-10-09-portable-workspace.md`. No se han modificado
ni eliminado fuentes externas. Tras la aprobación se añadió el paso obligatorio
de backswings indicado en las instrucciones actualizadas del repositorio.
