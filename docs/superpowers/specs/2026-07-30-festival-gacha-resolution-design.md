# Diseño: resolución fiable de Uberfest, Epicfest y Superfest

## Objetivo

Evitar que `fetch_bc_schedule.py` confunda Superfest con Uberfest o Epicfest cuando Ponos cambia el gato destacado o el texto promocional. La ejecución automática debe reconocer el Uberfest activo del 29 de julio de 2026 y generar un `id` coherente con su nombre.

## Causa raíz

El banner activo llega desde `gatya.tsv` con estos datos:

- ID de pool `1061`
- Texto `Squire Luno added! Special Capsules featuring powerful limited units!`
- Probabilidades: Rare `6470`, Super Rare `2600`, Uber Rare `900`, Legend Rare `30`

El catálogo no contenía ese texto exacto como alias de Uberfest. Un alias anterior de Superfest contenía casi el mismo texto y el matcher flexible lo seleccionaba por coincidencia parcial. Quitar ese alias evita el falso positivo, pero por sí solo deja el banner sin nombre canónico.

El Superfest anterior usó el ID `1051`, anunciaba a Lone Moon Lunos y tenía probabilidades `6470/2500/1000/30`. Por tanto, el gato anunciado no identifica de forma fiable el festival: los pools evolucionan y Superfest reúne unidades de Uberfest y Epicfest.

## Diseño

La resolución mantendrá las prioridades actuales, con dos defensas específicas:

1. `gacha_id_cache.json` seguirá siendo la fuente primaria. Se añadirá `1061 → Uberfest` y se conservará `1051 → Superfest`.
2. El alias exacto del texto actual se añadirá a Uberfest como respaldo.
3. El parser conservará las probabilidades de cada entrada del TSV.
4. Antes de aceptar una coincidencia para Uberfest, Epicfest o Superfest, se validará su firma de probabilidades:
   - Superfest: Super Rare `2500`, Uber Rare `1000`, Legend Rare `30`.
   - Uberfest/Epicfest: Super Rare `2600`, Uber Rare `900`, Legend Rare `30`.
5. Una coincidencia textual de Superfest con una entrada de 9% se rechazará, y una coincidencia textual de Uberfest/Epicfest con una entrada de 10% también se rechazará.
6. Una entrada de 10% con el texto genérico de cápsulas especiales podrá identificarse como Superfest aunque cambie el gato anunciado.
7. Una entrada desconocida de 9% no se adivinará como Uberfest o Epicfest si no existe un ID o alias fiable, porque ambas comparten las mismas probabilidades. En ese caso se conservará el texto de Ponos en vez de publicar un nombre canónico incorrecto.

Los arrays `ubers`, `legends` y demás gatos de `all_gachas_en.json` no se usarán para identificar el festival. Así, añadir o retirar gatos no afecta a la clasificación del calendario.

## Estructura del código

La lógica de resolución incrustada en `main()` se extraerá a una función pequeña que reciba una entrada ya parseada y las bases de nombres. Esto permite probar el comportamiento sin conectarse a Ponos ni escribir el JSON.

El flujo será:

`gatya.tsv → entrada con ID, texto y tasas → resolución por ID/alias → validación de firma fest → nombre canónico → id snake_case`

No se añadirá ninguna dependencia ni servicio externo al workflow.

## Datos actuales

La entrada de `gachas_eventos_actualizados_en1.json` se corregirá a:

- `id`: `uberfest_2026-07-29`
- `nombre`: `Uberfest`

Las fechas y características permanecerán sin cambios.

## Pruebas

Se añadirá una prueba unitaria sin red que cubra:

- ID `1061`, texto de Squire Luno y tasas `2600/900/30` resuelve a Uberfest.
- ID `1051`, texto de Lone Moon Lunos y tasas `2500/1000/30` resuelve a Superfest.
- Un alias de Superfest no puede clasificar una entrada de 9% como Superfest.
- Un futuro texto genérico de Superfest con un gato desconocido y tasas `2500/1000/30` resuelve a Superfest.
- Una entrada fest de 9% sin ID ni alias fiable conserva su nombre de origen.
- `_build_entry()` genera `uberfest_2026-07-29` cuando el nombre resuelto es Uberfest.

También se ejecutarán todas las pruebas existentes del repositorio y una validación JSON de los archivos modificados.

## Límites deliberados

Ponos no incluye en `gatya.tsv` la identidad completa del pool, solo su ID, texto y probabilidades. Uberfest y Epicfest tienen la misma firma de tasas, por lo que un ID completamente nuevo de uno de ellos no puede distinguirse matemáticamente usando solo ese TSV si el texto tampoco coincide con un alias. El comportamiento seguro será no adivinar. Superfest sí queda distinguido por su tasa de Uber Rare del 10%.
