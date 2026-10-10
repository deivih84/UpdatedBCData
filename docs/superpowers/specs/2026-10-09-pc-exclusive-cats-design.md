# Unidades exclusivas de PC en cats_data

Estado: diseño aprobado por el usuario; implementación pendiente de revisión del plan.

## Objetivo y alcance

Añadir los Ubers y otras unidades exclusivas de PC al catálogo de CatStats,
conservando sus IDs originales como referencia y sin alterar las IDs móviles.
Las unidades deben sobrevivir a la regeneración de `cats_data.json`.
El usuario aprobó la propuesta de IDs numéricas reservadas y fuente curada PC.

El alcance incluye la integración en UpdatedBCData y los cambios necesarios
en CatStats para admitir IDs dispersas, mostrar el origen PC y representar
datos desconocidos. No incluye gachas/calendarios PC, simulación PvP,
publicación, commit/push ni atribuir estadísticas móviles a versiones PC.

## Hallazgos que condicionan el diseño

- `scripts/data/actualizar_cats_info.py` reconstruye `units` desde `unit*.csv`
  de JP. El ID del JSON equivale al número del archivo menos uno.
- Actualmente `metadata.total_units` es la ID máxima más uno. El validador
  exige esa definición y rechaza cualquier unidad ajena a los CSV móviles.
- `update_cat_backswings.py` convierte las claves a enteros y busca archivos
  `cats/<id>.zip`. No hay fuentes PC verificadas en este flujo.
- En CatStats, `LocalCatDataSource.createUnitListFromResponse` recorre
  `0 until metadata.totalUnits`. No admite correctamente un contador real
  con claves dispersas. Las IDs son `Int`; el deserializador permite campos
  adicionales, pero el modelo actual no expone plataforma ni ID original.
- CatStats transforma filas estadísticas cortas rellenándolas con ceros.
  Esto no permite representar desconocidos de PC con fidelidad.
- CatStats calcula tiempos con convenciones de los CSV móviles y aplica
  un fallback de backswing cuando falta el valor. No se deben convertir los
  tiempos publicados en la wiki mediante fórmulas supuestas.

## Identidad

Reservar `[100000, 200000)` para PC. La clave de una unidad con ID PC numérica
verificada es `str(100000 + source_id)`; por ejemplo, Odin PC #911 se convierte
en `100911`. Se mantiene un registro curado permanente de identidad.

El importador rechaza IDs duplicadas, entradas móviles en el rango reservado,
IDs PC fuera de rango y desacuerdos entre clave, plataforma e ID original.
Nunca asigna IDs por nombre, posición o cantidad actual de unidades.
Las IDs móviles mantienen su representación habitual, como `000` y `881`.
Si una ficha no documenta la ID PC, permanece pendiente de identificación.

En `info` se añaden `platform: "pc"`, `source_id: "911"` y `source_url`.
Las entradas móviles sin `platform` se interpretan como `mobile` para
conservar compatibilidad. La app muestra `PC #911`, usando `100911` como
identidad interna para favoritos, imágenes y búsquedas internas.

## Fuente curada y datos incompletos

`data/inputs/cats_pc.json` será la fuente PC versionada. Incluye versión de
esquema, identidad, nombres por forma, rareza, obtención, URLs de referencia,
fecha de revisión y estado de verificación. El inventario inicial se toma
de las fichas de la wiki y se revisa unidad por unidad.

Se distinguen dos estados:

1. `verified`: estadísticas y conversión al esquema consumidor comprobadas.
   Puede incorporarse a `units` junto a los gatos móviles.
2. `catalog_only`: identidad/nombres verificados, estadísticas insuficientes.
   Se conserva en el catálogo curado y en un bloque adicional `pc_catalog`
   del JSON público. La app lo muestra como ficha PC sin cálculos de combate.

Cada dato estadístico lleva su nivel, unidades y condiciones de tesoros
cuando estén documentadas. Se usa `null` para lo desconocido en los datos
estructurados de la fuente. No se fabrican filas CSV completas rellenando
desconocidos con cero. Una ficha catalog_only no se convierte en un `Cat`
estadístico ni participa en comparaciones numéricas o recomendaciones.

Las habilidades PvP y otras propiedades sin equivalente móvil se conservan
como datos PC explícitos. La app puede mostrarlas descriptivamente; no les
asigna índices móviles ni las usa para simular combate.

## Generación y validación

La generación carga la fuente PC canónica desde `data/inputs`, validándola
antes de escribir. No depende de una copia antigua que haya quedado en
`workspace/data`. Fusiona las entradas verified después de generar los datos
móviles y conserva las fichas catalog_only en `pc_catalog`.

`metadata.total_units` pasa a ser `len(units)`, excluyendo `pc_catalog`.
Se añaden contadores explícitos para unidades móviles, PC verified y fichas
PC catalog_only. `metadata.version` sigue describiendo la extracción móvil;
la revisión de la fuente PC se registra aparte.

El validador sigue comparando todas las unidades móviles con sus CSV y
nombres. Valida las unidades PC y `pc_catalog` contra la fuente curada,
sin permitir que una marca `platform` arbitraria eluda controles. Cualquier
entrada extra sin fuente, colisión o discrepancia es un error.

## Animaciones e imágenes

Las unidades PC no buscan animaciones usando la ID móvil de igual número.
Mientras no haya fuentes PC verificadas, sus backswings son arrays de `null`
con una advertencia por forma. Nunca se deducen de la frecuencia de ataque.
Las fichas catalog_only no requieren un array de backswing.

Los ZIP y manifiestos móviles conservan sus contratos y fuentes PONOS.
No se crean ZIP PC ficticios ni se declaran como recursos móviles.
En CatStats se desactiva el visor cuando faltan recursos PC disponibles.

Las fotos verificadas usan la ID interna reservada dentro de `images/cats/`
y el convenio de nombres actual de la app. Se preservan los originales,
URLs existentes y fotos anteriores si una descarga falla. No se publica
una imagen bajo la ID móvil `911` para representar a Odin PC.

## Cambios de CatStats

La carga recorre las entradas reales de `units`, ordenadas por ID numérica,
en lugar de recorrer un rango basado en `total_units`. Se revisan los demás
usos de contadores, índices e IDs para no asumir contigüidad.

Se amplía el modelo con plataforma, ID original y catálogo PC. Las fichas
PC muestran la etiqueta «Exclusivo de PC» y la referencia original.
Las fichas incompletas muestran los campos conocidos y su disponibilidad;
no presentan ceros como estadísticas ni valores derivados sin fundamento.
La app mantiene el comportamiento existente para los gatos móviles.

El cambio del significado de `total_units` requiere coordinar datos y app:
primero se adapta y verifica la app; después se exporta el nuevo formato.
No se publican los datos como compatibles con versiones antiguas.

## Verificación y aceptación

- Tests con fixtures: colisiones, identidad estable, conservación al
  regenerar, contador real, datos PC incompletos y cobertura móvil intacta.
- Tests de app: carga de IDs dispersas, catálogo incompleto, etiqueta/ID PC,
  ausencia de cálculos inventados y ausencia de descarga de ZIP móvil ajeno.
- Revisar las fichas importadas contra sus fuentes; comunicar cuántas quedan
  verified y cuántas catalog_only, sin afirmar cobertura completa sin comprobarla.
- Validación de código de solo lectura hasta aplicar los datos autorizados.
- Antes de escribir datos: `check_project.py --game-data` y
  `update_all.py --dry-run`; inspeccionar salidas parciales si hay fallos.
- Tras aplicar: sincronizar animaciones móviles, recalcular backswings y
  ejecutar los dry-runs finales. Deben indicar cero paths y cero unidades
  cambiadas respectivamente; las advertencias siguen visibles.
- Ejecutar la suite unittest y `git diff --check`; revisar outputs públicos
  e inputs curados. No exportar ni publicar antes de verificar la app.

## Referencias consultadas

- [Inventario de contenido PC de la wiki](https://battle-cats.fandom.com/wiki/Category%3APC_Exclusive_Content).
- [Battle God Odin, PC #911](https://battle-cats.fandom.com/wiki/Battle_God_Odin_%28PC_Uber_Rare_Cat%29).
- [Type-Monshiro](https://battle-cats.fandom.com/wiki/Type-Monshiro_%28PC_Uber_Rare_Cat%29):
  ejemplo de estadísticas y habilidades PvP que requieren interpretación explícita.

La disponibilidad de las fichas web varía; los errores de descarga no
constituyen evidencia de datos ausentes ni permiten inferir sus valores.
