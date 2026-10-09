# UpdatedBCData

Datos públicos de Battle Cats y herramientas para mantenerlos. El repositorio
contiene calendarios EN/JP, catálogos, imágenes, estadísticas, stages y ZIPs de
animaciones. Los generadores antes repartidos entre Descargas y CatStats ahora
están en `scripts/`; el flujo completo se inicia con `update_all.py`.

Para agentes de IA, leer primero [AGENTS.md](AGENTS.md). El mapa de componentes
está en [docs/architecture.md](docs/architecture.md).

## Instalación en Windows

Requiere Git y Python **3.12**. En PowerShell:

```powershell
git clone https://github.com/deivih84/UpdatedBCData.git
cd UpdatedBCData
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe check_project.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Se puede activar el entorno con `.\.venv\Scripts\Activate.ps1`; usar su Python
directamente evita depender de la política de ejecución de PowerShell.

## Instalación en Linux

Con Git, Python 3.12 y el módulo `venv` instalado:

```bash
git clone https://github.com/deivih84/UpdatedBCData.git
cd UpdatedBCData
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python check_project.py
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

En Ubuntu, si faltan dependencias del sistema, instalar `python3.12-venv`,
`libgl1` y `libegl1`. Qt es una dependencia de importación de tbcml; estos
comandos no necesitan una sesión gráfica. La CI ejecuta los tests en Windows y
Ubuntu con Python 3.12.

En los ejemplos siguientes, `python` representa el Python de ese entorno.

## Calendarios y catálogos online

No necesitan CatStats ni una extracción local de BCData:

```bash
python sync_gacha_catalog.py --online --dry-run
python sync_gacha_catalog.py --online
python fetch_bc_schedule.py
python fetch_bc_events.py --online
python sync_gacha_catalog.py --region jp --online
python fetch_bc_schedule.py --region jp
```

Estos comandos acceden a fuentes remotas; sin `--dry-run` actualizan datos e
imágenes. La suite de tests usa fixtures y no publica calendarios.

## Regenerar estadísticas y animaciones

Este flujo necesita **BCData extraído y los paquetes fuente conservados**.
Consulta [docs/workspace.md](docs/workspace.md) para configurar fuentes y app.
BCData se detecta en `../BCData`; también puede configurarse dentro de
`workspace/BCData` o en cualquier otra ruta. Un clon del espejo puede estar
retrasado y no sustituye los APK/XAPK/APKS originales necesarios.

```bash
python check_project.py --game-data
python update_all.py --list
python update_all.py --dry-run
python update_all.py
python update_cat_animations.py --dry-run
python update_cat_backswings.py --dry-run
python -m unittest discover -s tests -p 'test_*.py' -v
```

El `--dry-run` del orquestador valida rutas y muestra comandos; no calcula los
cambios de cada generador. Una reparación de animaciones incluye backswings:

```bash
python update_all.py --only animations
```

Para copiar resultados a una app configurada:

```bash
python update_all.py --export-app
```

El pipeline no hace pull, commit o push por defecto. `--skip-pull` se conserva
por compatibilidad. `--push` solicita expresamente commit/push de los outputs
seleccionados y rechaza cambios ajenos ya staged. Un fallo detiene los pasos
posteriores; revisar los outputs parciales antes de reintentar.

## Qué llevar a otro ordenador

Git transporta código, documentación, inputs curados y outputs públicos.
`workspace.local.json`, credenciales, entornos virtuales y `workspace/` se
quedan en cada máquina. Para regenerar una versión concreta, conservar también
las extracciones y **todos los paquetes incrementales** de BCData utilizados.
CatStats es un checkout opcional para exportar assets y drawables.

Los APK de juego descargados van en BCData/workspace, nunca en los archivos
temporales a stagear. El APK de la app ya publicado en este repo se conserva.

Consulta el [inventario de migración](docs/migration-inventory.md) para saber
qué herramientas se incorporaron y cuáles son históricas.
