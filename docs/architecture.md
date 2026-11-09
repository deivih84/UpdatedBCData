# Mapa operativo

| Tarea | Entrada oficial | Fuentes | Outputs |
|---|---|---|---|
| Gacha EN/JP | `sync_gacha_catalog.py`, `fetch_bc_schedule.py` | PONOS, Godfat, wiki, BCData opcional | Catálogos/cache/estado por región, calendarios, `images/gacha` |
| Eventos EN | `fetch_bc_events.py` | sale.tsv PONOS, fallback Godfat, índice EN, wiki | Calendario EN, catálogo/índice/estado, `images/events` |
| Datos completos | `update_all.py` | BCData, inputs curados, wiki para nombres | cats/enemies/stages JSON, animaciones, backswings |
| Animaciones | `update_cat_animations.py` | Paquetes incrementales BCData | `cats/<id>.zip`, `cats/manifest.json`, bloque de versión |
| Backswings | `update_cat_backswings.py` | JSON de gatos y animaciones fusionadas | Arrays por forma en cats_data.json |
| Resúmenes | `scripts/data/build_update_summary.py` | JSON públicos y versión explícita | `update_summaries`, borrador/informe/manifiesto |
| Validación de gatos | `scripts/tools/validate_cats_data.py` | JSON, DataLocal y nombres de la versión | Informe de integridad; ver `--help` |
| Diagnóstico local | `check_project.py` | Archivos y módulos instalados | Informe de solo lectura |

El pipeline ejecuta names → combos → talents → enemies_csv → enemies_json →
stages → cats_info → evolution → animations → backswings. Los combos usan la
extracción más reciente de EN/JP (EN en caso de empate), conservando los nombres
curados y alineando las nuevas filas con su índice fuente. Las fases conservan
el catálogo EN y añaden los capítulos/mapas exclusivos de JP cuando JP va por
delante; se unen por ID, nunca por similitud de nombres. Los mapas del coliseo
mantienen sus restricciones por separado aunque compartan título. Stats,
talentos y evolución usan JP. Las descripciones multilingües tienen herramientas
opcionales en `scripts/data`.

`enemies_csv` también obtiene las duraciones de ataque de los paquetes JP
conservados y guarda `enemy_attack_animations.json` entre los inputs curados.
Cada registro identifica enemigo, animación, SHA-256, región y versión fuente.
El generador de enemigos conserva las frecuencias históricas revisadas y usa
estas duraciones para completar los intervalos CSV cero que carecen de fallback;
las ausencias siguen produciendo advertencias visibles. La caché puede usarse
sin el paquete, pero recalcularla exige conservar los instaladores y Android
`aapt` (SDK o PATH).

Los nombres curados se completan con el nombre JP oficial de una ultraforma
cuando `unitbuy.csv` declara su evolución y la localización contiene la cuarta
forma. El validador comprueba ese mínimo independientemente del listado de
nombres para detectar recortes silenciosos.

`workspace_paths.py` contiene únicamente resolución, selección semántica y
preparación explícita de inputs. Importar módulos no escribe datos ni busca
una extracción obligatoria. Los entrypoints de la raíz mantienen los imports
y comandos existentes; los scripts incorporados soportan ejecución directa
o por módulo.

`data/inputs` es estado curado versionable; `workspace/data` es el espacio de
trabajo. Los JSON públicos de la raíz y los directorios de imágenes/animaciones
mantienen sus rutas para versiones anteriores de la app. CatStats es un
destino opcional, no la fuente obligatoria de intermedios.

Un fallo del pipeline deja visibles sus outputs parciales, detiene los pasos
posteriores y evita exportación/push. Las transacciones propias de catálogo y
animaciones conservan sus garantías existentes. No hay una transacción global
de todos los generadores; revisar antes de reintentar o publicar.
