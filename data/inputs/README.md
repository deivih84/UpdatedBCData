# Inputs curados

Semillas procedentes de los assets de CatStats durante la migración. Se
versionan porque incluyen nombres publicados, combos acumulados y excepciones
personalizadas de talentos que no se deben reconstruir solo con el remoto.

- `names.txt`: nombres y formas de unidades; se preserva la localización ya publicada.
- `cats_pc.json`: catálogo PC revisado, IDs reservadas, formas y mediciones publicadas; véase [pc-cats](../../docs/pc-cats.md). Es la fuente canónica y se lee directamente, sin depender de copias de trabajo antiguas.
- `combos.csv`, `combo_names.txt`: estado acumulado del sincronizador incremental.
- `skill_acquisition.csv`: conserva las filas protegidas 105, 107, 258, 259 y 261.
- `skill_level.csv`: tabla de costes NP leída por el generador de gatos.
- `enemy_data.csv`: semilla de stats para el generador independiente de enemigos.
- `backswings.txt`, `enemy_backswings.txt`: lookups históricos, el segundo sigue siendo input del generador de enemigos.
- `descriptions/<lang>/enemy_*.tsv`: nombres y descripciones multilingües.

El pipeline crea copias de trabajo solo si faltan. Tras éxito guarda los
inputs acumulativos correspondientes a sus pasos; revisar el diff antes de
publicar. No añadir aquí APK, tokens, caches o JSON intermedios de la app.
