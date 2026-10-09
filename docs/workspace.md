# Configuración portable del workspace

La raíz se deriva del archivo Python, no del directorio actual de la shell.
Las rutas relativas de configuración y los overrides del pipeline se resuelven
desde esa raíz. Los argumentos de archivos específicos de los sincronizadores
conservan su semántica CLI existente.

## Configuración local

Copiar `workspace.example.json` a `workspace.local.json` y ajustar las rutas.
PowerShell: `Copy-Item workspace.example.json workspace.local.json`.
Linux: `cp workspace.example.json workspace.local.json`.

Ejemplo si los tres proyectos se clonan como carpetas hermanas:

```json
{
  "bcdata": "../BCData",
  "catstats": "../CatStats",
  "data": "workspace/data",
  "image_inbox": "workspace/images",
  "app_drawables": null
}
```

También se admiten rutas absolutas propias en este archivo **ignorado por Git**.
No se copian al repo las de otro usuario. Un valor desconocido o JSON inválido
produce un error, evitando ignorar una configuración mal escrita.

La migración conserva la ruta actual de CatStats en `workspace.local.json`
del ordenador original. Ese archivo está ignorado; cada clon configura su
propio destino de app si quiere exportar.

| Clave | Variable de entorno | Uso |
|---|---|---|
| `bcdata` | `BCDATA_DIR` | Checkout con extracciones y paquetes |
| `catstats` | `CATSTATS_DIR` | Checkout opcional de la app |
| `data` | `UPDATED_BCDATA_WORK_DATA` | Copias de trabajo de inputs/intermedios |
| `image_inbox` | `UPDATED_BCDATA_IMAGE_INBOX` | Entrada de imágenes nuevas |
| `app_drawables` | `UPDATED_BCDATA_APP_DRAWABLES` | Override opcional del destino de imágenes |

Precedencia: argumento explícito, entorno, configuración local, valor por
defecto. El destino de drawables también admite el campo histórico
`appDrawables` de los configs de sincronización; se mantiene `null` en Git
para utilizar la configuración común. La selección explícita de drawables
tiene prioridad. No se condiciona la exportación al sistema operativo.

Los procesos hijos reciben las rutas efectivas. Para un paso aislado:

```bash
python update_all.py --bcdata ../BCData --only cats_info evolution
python update_all.py --catstats ../CatStats --only backswings --export-app
```

Las opciones CLI de un generador importado individual se limitan a `--help`;
sus rutas se configuran por el archivo común o el entorno. Utilizar el
orquestador para conservar inputs curados y exportar resultados.

## BCData y reproducción de una versión

El checkout puede obtenerse de `https://github.com/deivih84/BCData.git`.
Para extraer paquetes, seguir el README de ese repo. La extracción pertenece
a BCData; aquí están los consumidores y generadores de los datos públicos.
No se descargan nuevas versiones ni se ejecuta `git pull` automáticamente.

Estructura esperada:

```text
BCData/
  latest.txt
  <version>jp/DataLocal/
  <version>jp/resLocal/
  <version>en/DataLocal/
  <version>en/resLocal/
  ... paquetes .apk, .xapk, .apks o .apkm conservados ...
```

Los generadores seleccionan versiones semánticamente, con EN y JP
independientes. Se preservan recursos de idiomas cuando no hay una extracción
nueva disponible. `check_project.py --game-data` verifica fuentes básicas;
`update_all.py --dry-run` valida las requeridas por los pasos elegidos. La
comprobación definitiva de packs y coherencia de versión es el dry-run de
`update_cat_animations.py`.

Los packs son incrementales: conservar cada fuente aplicada y todas las nuevas
en orden semántico. No reemplazar un archivo `cats/<id>.zip` con un pack parcial.
La animación final y el backswing se verifican por separado; las formas ausentes
quedan como advertencias visibles y los backswings desconocidos como `null`.

## Inputs, trabajo local y exportación

`data/inputs` contiene las semillas curadas necesarias. El pipeline las copia
a `workspace/data` solamente si falta el archivo; no sobrescribe trabajo local.
Después de un pipeline exitoso, names, combos, talentos y enemy CSV de los
pasos ejecutados se guardan de vuelta en `data/inputs`. Revisar estos cambios
junto con los JSON. Los cinco IDs de talentos protegidos se conservan.

Si se cambia a una fuente histórica distinta, usar otro directorio de trabajo
con `--work-data workspace/mi-version` para no mezclar datos acumulativos.
Las semillas versionadas representan el estado actual, no una copia de cada
versión histórica; conservar snapshots Git para reproducir estados anteriores.

La generación no requiere la app. `--export-app` copia JSON finales y inputs
correspondientes a los pasos seleccionados, después de su éxito. Los
sincronizadores de imágenes copian a drawables cuando están configurados.
Los scripts opcionales de descripciones escriben en `workspace/data/descriptions`;
su exportación se hace explícitamente a `CatStats/app/src/main/assets/data/descriptions`.

## Imágenes y herramientas históricas

```bash
python scripts/tools/actualizar_imagenes.py --source data/image-inbox --kind cats
python scripts/tools/actualizar_imagenes.py --source workspace/images --kind enemies
```

Las imágenes van a `images/cats` o `images/enemies` y, si se configura, a
drawables. Los originales se conservan. El recorte de gatos es de 110×85;
enemigos conservan sus dimensiones. Las utilidades de recorte/renombrado en
el mismo directorio requieren un argumento de carpeta y pueden modificarla;
no usar esos comandos sobre la raíz del repo.

Los scripts de `scripts/legacy` no forman parte del flujo automático.
El backswing de gatos vigente procede de animaciones; el scraper histórico
solo se conserva como referencia. Los bots requieren
`requirements-legacy.txt`, `DISCORD_TOKEN` y `GITHUB_TOKEN` en el entorno.
Ejecutarlos activa una conexión Discord y puede publicar cambios; nunca
usarlos como comprobación de instalación.

## Dependencias

`requirements-lock.txt` fija las dependencias de mantenimiento para Python 3.12
y Windows/Linux. `requirements.txt` define los rangos de actualización;
`requirements-gacha-sync.txt` conserva la interfaz del job online existente.
El lock se genera con:

```bash
uv pip compile requirements.txt --universal --python-version 3.12 --output-file requirements-lock.txt
```

Después de actualizarlo, instalar y ejecutar la suite en ambos sistemas.
El bundle Qt para Windows tiene una restricción específica en requirements
porque las versiones más nuevas no publican su wheel para ese sistema.
