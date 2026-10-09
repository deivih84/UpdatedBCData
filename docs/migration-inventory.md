# Inventario de la migración portable

Migración iniciada el 9 de octubre de 2026. Las fuentes externas originales
se conservan; utilizar desde ahora los comandos de este repo. Los checksums
originales auditados están en [migration-source-checksums.json](migration-source-checksums.json).
Ese inventario registra fuentes revisadas, incluidas algunas herramientas de
app que se clasificaron y no se incorporaron.

| Procedencia | Destino | Decisión |
|---|---|---|
| `Automatizacion/update_all.py` | `update_all.py` | Orquestador adaptado con configuración común, preflight y parada ante fallos |
| `Automatizacion/actualizar_{cats_info,combo_data,descripciones,descripciones_enemigos,enemies,evolution_costs,names,names_enemigos,talentos}.py` | `scripts/data` | Generadores incorporados; fuentes/outputs portables |
| `Automatizacion/actualizar_imagenes.py` | `scripts/tools` | Adaptado; conserva originales y escribe ambos destinos configurados |
| `Automatizacion/images/{cambiarnombrescompose,redimensionarcatunits}.py` | `scripts/tools` | Importación segura, carpeta explícita |
| `Automatizacion/images/*.png` | `data/image-inbox` | Seis entradas pendientes conservadas; no publicadas automáticamente |
| `Automatizacion/{backswings,enemy_backswings}.py` | `scripts/legacy` | Scrapers históricos; help no inicia red |
| `Automatizacion/Pruebas gatchas/{mapear_gatchas.py,names.txt,gatchas.txt}` | `scripts/legacy` | Mapeo manual histórico separado del catálogo automático |
| Bots locales ignorados de la raíz | `scripts/legacy/bot_updater_*.py` | Copias versionables con tokens extraídos al entorno |
| `CatStats/scripts/{build_enemies_json,parse_stages}.py` | `scripts/data` | Ya no requieren el árbol de la app |
| `CatStats/scripts/{build_update_summary,update_summary_core}.py` | `scripts/data` | Resúmenes con raíz portable y dependencia local |
| `CatStats/scripts/update_summary_agent_prompt.md` | `docs` | Guía de resumen incorporada |
| `CatStats/scripts/{validate_cats_data,update_medals}.py` | `scripts/tools` | Utilidades explícitas; medallas escribe stages público |
| `CatStats/assets/data/descriptions/de/renom.py` | `scripts/tools/rename_descriptions.py` | Función normalizadora sin ejecución al importar |
| `CatStats/assets/data` | `data/inputs` | Nombres, combos, skill acquisition/level, enemy CSV, backswings y 18 TSV de nombres/descripciones enemigos |
| Tests de Automatizacion | `tests/test_data_generators.py`, `tests/test_update_all.py` | Contratos adaptados y ampliados para fixtures independientes |
| Tests de stages dependientes de extracción real | Tests de funciones/fixtures + validación opcional con BCData | No convertir datos locales de juego en requisito de la suite de instalación |

Se excluyen del traslado los APK y extracciones de BCData, la app Android
completa, herramientas de build/release de la app, caches/venvs y copias
generadas de descripciones de unidades reconstruibles desde BCData. También
se conserva el empaquetador antiguo de animaciones en CatStats, pero no se
adopta: el flujo oficial aquí fusiona packs incrementales.

Los planes anteriores que apuntan a carpetas personales son históricos; las
instrucciones vigentes son README, AGENTS y docs/workspace. Los comandos
antiguos de Descargas pueden seguir existiendo, pero no se sincronizarán con
esta nueva fuente oficial.

Los cambios de cats_data.json, data_version.json y el nuevo updater de
backswings ya estaban presentes al iniciar la implementación. Se preservan;
la reorganización no ejecuta una actualización online ni regenera estos datos
para probar portabilidad.
