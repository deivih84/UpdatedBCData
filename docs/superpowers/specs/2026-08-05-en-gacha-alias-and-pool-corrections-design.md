# Diseño: correcciones EN de alias y pools de gachas

## Objetivo

Normalizar cuatro banners que PONOS publica con textos promocionales y asegurar
que los pools de `Epicfest` y `Gals of Summer Sunshine` representen las unidades
EN disponibles.

## Cambios de datos

`all_gachas_en.json` conservará los nombres canónicos existentes y asociará los
textos de PONOS de la siguiente forma:

- `Limited Summer capsules with a exciting hero! Tap banner for info!` → `Gals of Summer Sunshine`.
- `Mamoluga added! Unstoppable Eldritch Cats(?)!` → `Luga Families`.
- `Mighty Morta-Loncha added! Ultimate anti-Zombie firepower!` → `Iron Legion`.
- `Lone Moon Lunos added! Special Capsules featuring powerful limited units!` → `Epicfest`.

El calendario `gachas_eventos_actualizados_en1.json` reemplazará, para todas
las campañas afectadas, tanto `nombre` como el prefijo de `id` por su nombre
canónico. Las fechas y las características no cambian.

El pool Uber Rare de `Gals of Summer Sunshine` será `[820, 714, 564, 438, 354,
275]`: Seaside Pegasa, Coastal Explorer Kanna, Summerluga, Waverider Kuu,
Seashore Kai y Midsummer Rabbit. Se eliminan los tres Uber Rare exclusivos de
Blue Ocean que estaban mezclados en ese pool.

El pool Uber Rare de `Epicfest` incluirá `859` (Lone Moon Lunos), además de
la unidad Epicfest ya registrada `787` (Netherworld Nymph Lunacia).

## Resolución y regresión

Los cuatro textos completos se añaden como aliases exactos. Esto permite que
una siguiente ejecución de `fetch_bc_schedule.py` genere directamente los
nombres canónicos. La prueba de resolución que hoy trata Lone Moon Lunos como
Superfest se sustituye por una que exige Epicfest con su firma de tasas de 9%.

Las pruebas nuevas validarán las dos listas de Uber Rare contra `cats_data.json`
y comprobarán que las entradas de calendario afectadas ya no contienen los
nombres promocionales.

## Límites

No se regenerará el calendario desde red: se corrigen las campañas ya descargadas
y los aliases que usarán futuras descargas. No se cambian las unidades, fechas,
tasas ni banners ajenos a los cuatro casos.
