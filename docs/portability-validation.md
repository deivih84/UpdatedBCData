# Validación de portabilidad

Comprobaciones realizadas en Windows el 9 de octubre de 2026 con Python 3.12.15.

- Instalación nueva de `requirements.txt` y comprobación posterior contra
  `requirements-lock.txt`: 30 dependencias instaladas.
- Suite final: **183 tests, todos correctos** (la base previa tenía 148).
- Copia limpia de 1.622 archivos versionables, en una ruta con espacios, sin
  configuración local, credenciales, workspace previo, BCData ni CatStats:
  diagnóstico, listado del pipeline y los 183 tests correctos.
- Los entrypoints modernos e importados mostraron `--help` desde una carpeta
  externa sin crear intermedios ni modificar la copia. Los imports de
  utilidades de imágenes se comprobaron con un archivo testigo cuyo nombre y
  bytes se conservaron.
- Hashes de archivos de la copia limpia iguales a sus originales tras la
  validación; no se regeneraron datos públicos ni se ejecutaron bots Discord.
- `update_cat_animations.py --dry-run`: ninguna fuente pendiente,
  14.839 recursos conservados, ningún ZIP creado/modificado, **0 changed paths**.
- `update_cat_backswings.py --dry-run`: **0 changed units**, 56 formas sin valor
  calculable, con advertencias visibles.
- Lock instalado también en un target de wheels Linux x86_64/Python 3.12:
  todas las dependencias disponibles como paquetes binarios.
- `git diff --check` y compilación de módulos Python correctos; sin tokens
  literales en las herramientas incorporadas.

La revisión independiente encontró dos problemas: rollback de metadata ante
fallo de resúmenes y selección de una carpeta vacía en stages. Se reprodujeron
en tests antes de corregirlos; sus regresiones forman parte de la suite final.

**Límite:** no se ha ejecutado Python dentro de Linux. El motor Docker local
no estaba disponible; comprobar wheels no equivale a probar un runtime Linux.
La CI añadida ejecutará la suite en Windows y Ubuntu cuando se publiquen los
cambios. Tampoco se ha ejecutado una regeneración completa online del juego:
esta tarea valida portabilidad y conserva los datos públicos existentes.

Las extracciones y todos los paquetes incrementales de BCData deben
transportarse/obtenerse aparte para regenerar una versión concreta. El clon
Git incluye las herramientas, semillas curadas y datos públicos, no todas
las fuentes originales de PONOS.
