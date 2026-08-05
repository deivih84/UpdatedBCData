# Diseño: Summer Break Cats Paradise y pool Sunshine

## Objetivo

Corregir la identidad del Event Capsule programado como `Limited Capsules` y
mostrar su banner actualizado. Corregir además la rotación EN actual de seis
Uber Rare en `Gals of Summer Sunshine`.

## Datos canónicos

El banner de Event Capsule se llamará `Summer Break Cats Paradise`. El catálogo
conservará `Summer Break Capsules Paradise` y `Limited Capsules` como aliases
para reconocer tanto datos históricos como el texto actual de PONOS. La entrada
del calendario del 15 al 28 de agosto de 2026 usará el nombre canónico y el ID
`summer_break_cats_paradise_2026-08-15`.

El pool `gatos_ids` existente se conserva: `[342, 375, 822, 870]` (Maneki Cat,
Coin Cat, Consultant Cat y Ancient Egg: N207/Tycoon Cat). La imagen proporcionada
reemplaza `images/gacha/banner_gatcha_summer_break_paradise.png`, cuya URL ya usa
el catálogo.

La lista Uber Rare de `Gals of Summer Sunshine` queda exactamente en
`[820, 666, 563, 438, 354, 275]`: Seaside Pegasa, Night Beach Lilin, Squirtgun
Saki, Waverider Kuu, Seashore Kai y Midsummer Rabbit. Coastal Explorer Kanna
(`714`) y Summerluga (`564`) no pertenecen a esta rotación.

## Pruebas

Las pruebas comprobarán la resolución de `Limited Capsules`, los cuatro gatos
del Event Capsule, los seis Uber Rare de Sunshine y la entrada canónica del
calendario. Se validarán JSON, el `dry-run` de animaciones y toda la suite.

## Límites

No se altera el pool de Blue Ocean, las fechas, las características ni otros
recursos de imagen. El binario nuevo se copia únicamente al banner gacha que
ya referencia `all_gachas_en.json`.
