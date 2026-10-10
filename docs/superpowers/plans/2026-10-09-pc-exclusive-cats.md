# PC Exclusive Cats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execution method requires user selection; native execution is recommended here.

**Goal:** Incorporate PC-exclusive cats into the public data and CatStats without ID collisions, lost curated records, or invented combat statistics.

**Architecture:** UpdatedBCData owns a reviewed PC source and merges it with generated mobile data. CatStats loads sparse numeric IDs and displays incomplete PC records separately from combat-capable units. Both repositories adopt the same PC identity and field contract before exporting the new data.

**Tech Stack:** Python 3.12, existing locked Python dependencies, unittest; Kotlin/Jetpack Compose, kotlinx.serialization, JUnit and Android instrumentation.

**Spec:** `docs/superpowers/specs/2026-10-09-pc-exclusive-cats-design.md`

## Global Constraints

- Reservar `[100000, 200000)` para PC.
- La clave de una unidad con ID PC numérica verificada es `str(100000 + source_id)`.
- Las IDs móviles mantienen su representación habitual, como `000` y `881`.
- `metadata.total_units` pasa a ser `len(units)`, excluyendo `pc_catalog`.
- Las unidades PC no buscan animaciones usando la ID móvil de igual número.
- No se fabrican filas CSV completas rellenando desconocidos con cero.
- Una ficha catalog_only no se convierte en un `Cat` estadístico ni participa en comparaciones numéricas o recomendaciones.
- No incluye gachas/calendarios PC, simulación PvP, publicación, commit/push ni atribuir estadísticas móviles a versiones PC.
- Resolve repository inputs from module paths/Workspace, never personal absolute paths.
- Use UpdatedBCData generators; historical app/Downloads generators are not execution entrypoints.
- Preserve both repositories' existing tracked and untracked edits. Do not reset, stash, stage, or commit them.

## Review Focus

1. A forged `platform: pc` on a mobile ID must fail rather than bypass CSV validation (Task 2).
2. A cached old PC source in workspace/data must not mask the updated canonical seed (Task 2).
3. Failed remote refresh/coroutine cancellation must retain the previous valid PC catalog without mixing data from different responses (Task 4).
4. A sparse mobile catalog must load every actual key without requiring contiguous IDs or adding nonexistent units (Task 3).
5. A PC name matching a mobile name must keep its separate identity and never borrow mobile stats/artwork/animation resources (Tasks 1, 5, 6).

## Repository and file map

`U` denotes the current UpdatedBCData root, resolved via `workspace_paths.ROOT`.
`A` denotes `Workspace.load().catstats`; fail clearly if absent for app work.
Paths below are relative to their corresponding root. Read each root's AGENTS.md.

UpdatedBCData:

- Create `scripts/data/pc_cats.py`: identity, source validation, merge and counters.
- Create `data/inputs/cats_pc.json`: reviewed PC records, no runtime caches.
- Modify `scripts/data/actualizar_cats_info.py`: canonical PC merge before writing.
- Modify `scripts/tools/validate_cats_data.py`: mobile and curated PC coverage.
- Modify `update_cat_backswings.py`: explicit unavailable PC animations.
- Create `tests/test_pc_cats.py`, `tests/test_pc_cats_validation.py`.
- Extend `tests/test_data_generators.py`, `tests/test_cat_backswings.py`.
- Create `docs/pc-cats.md`; update `data/inputs/README.md`, `docs/architecture.md`.
- Public output: `cats_data.json`; verified PC photos under `images/cats/`.

CatStats:

- Modify `app/src/main/java/cat/battlestats/model/CatsDataResponse.kt`.
- Create `app/src/main/java/cat/battlestats/model/PcCatCatalog.kt`.
- Create `app/src/main/java/cat/battlestats/persistence/CatDataEntries.kt`.
- Modify `app/src/main/java/cat/battlestats/persistence/LocalCatDataSource.kt`.
- Modify `app/src/main/java/cat/battlestats/persistence/CatRepository.kt`.
- Modify `app/src/main/java/cat/battlestats/model/viewModels/MainViewModel.kt`.
- Modify `app/src/main/java/cat/battlestats/model/CatUnit.kt`.
- Modify `app/src/main/java/cat/battlestats/ui/screens/CatsScreen.kt` and `CatDetailScreen.kt`.
- Create `app/src/main/java/cat/battlestats/ui/screens/PcCatCatalogSection.kt`.
- Modify default and Spanish string resources; default resources provide fallback for other locales.
- Create JVM tests in `app/src/test/java/cat/battlestats/persistence/PcCatsDataTest.kt` and `app/src/test/java/cat/battlestats/model/PcCatCatalogTest.kt`.
- Create instrumentation test `app/src/androidTest/java/cat/battlestats/PcCatCatalogTest.kt`.
- Extend existing `CatsDataAssetCompatibilityTest.kt` without removing prior assertions.

## Shared data contract

The canonical source has `schema_version: 1`, `reviewed_at` (ISO date), and an
`entries` array. Each entry has a decimal-string `source_id`, `status`, `info`,
`forms`, and, for verified entries only, `stats` and `conversion_evidence`.
The internal ID is derived rather than assigned by array order.

Example catalog-only record, with no claim that numeric stats were verified:

```json
{
  "source_id": "911",
  "status": "catalog_only",
  "info": {
    "platform": "pc",
    "source_id": "911",
    "source_url": "https://battle-cats.fandom.com/wiki/Battle_God_Odin_%28PC_Uber_Rare_Cat%29",
    "rarity": "UR",
    "name_basic": "Battle God Odin",
    "names_evolved": "Odin End",
    "obtain_method": "PC exclusive — VIP The Almighties The Majestic Zeus"
  },
  "forms": [
    {"code": "f", "name": "Battle God Odin", "measurements": [], "abilities": []},
    {"code": "c", "name": "Odin End", "measurements": [], "abilities": []}
  ]
}
```

`measurements` uses objects `{field, value, unit, level, treasures, source_url}`;
unknown `value`, `level`, or `treasures` is null. Values are numbers or null,
units/conditions are explicit strings or null. Allowed fields initially:
`health`, `damage`, `range`, `speed`, `knockbacks`, `cost`, `foreswing`,
`attack_frequency`, `recharge_time`. No multiplier inference from missing context.
Abilities use `{text, pvp_only, source_url}`. Form codes follow `f,c,s,u`, with
one to four actually documented forms. Source IDs without verification are
listed in the import report, not given a synthetic numeric ID.

For a verified record, `stats` must match the number/order of forms and contain
numeric rows in the existing mobile schema. `conversion_evidence` provides
per-form mappings `{form, column, source_url, explanation}` covering every
numeric column, including verified absence/defaults and timing conversions.
An uncovered column prevents promotion to verified; zero is not a missing value.
Catalog-only records are expected to be the initial majority; the implementation
must report actual verified/catalog-only counts rather than promise a promotion.

Public `units[internal_id]` receives verified `info`, `stats`, `pc_forms`, and
null `backswing` entries. `pc_catalog[internal_id]` receives catalog-only `info`
and `forms`. A record cannot appear in both. Metadata adds `mobile_units`,
`pc_units`, `pc_catalog_units`, `pc_source_revision` alongside the existing
mobile version and last-update fields.

## Task 1: Stable PC identity and reviewed source validation

**Interfaces produced:**

```python
def pc_key(source_id: str) -> str: ...
def load_pc_source(path: Path) -> dict: ...
def merge_pc_source(data: dict, source: dict) -> dict: ...
```

`load_pc_source` validates the entire document and raises ValueError before any
mutation. `merge_pc_source` returns a deep copy with canonical PC entries and
counters, replacing previous PC-derived blocks without touching mobile values.

- [ ] Record git status/diffs in both repositories, read applicable instructions, and establish execution isolation with using-git-worktrees. Preserve uncommitted app edits when creating an isolated checkout; do not use a bare HEAD worktree that silently drops them.
- [ ] Add failing unittest fixtures for duplicate IDs, negative/noncanonical IDs, form mismatches, zero mistaken for unknown, missing conversion evidence, overlapping mobile IDs, and reordered source entries. A catalog-only fixture requires no synthetic stats.

```python
def test_pc_id_is_independent_of_source_order(self):
    self.assertEqual(pc_key("911"), "100911")
    self.assertEqual(pc_key("912"), "100912")

def test_pc_source_never_overwrites_mobile(self):
    before = {"metadata": {"version": "15.7.1"}, "units": {"911": mobile_fixture()}}
    after = merge_pc_source(before, odin_catalog_fixture())
    self.assertEqual(after["units"]["911"], before["units"]["911"])
    self.assertIn("100911", after["pc_catalog"])
    self.assertNotIn("100911", after["units"])
```

Fixture factories are local to `tests/test_pc_cats.py`; create minimal mobile
info/stats dictionaries and the exact Odin example above in those factories.

- [ ] Run `.venv/Scripts/python.exe -m unittest discover -s tests -p test_pc_cats.py -v`; confirm failing imports/assertions identify the missing behavior.
- [ ] Implement the three functions in `scripts/data/pc_cats.py`, using deep copies, finite numeric checks, duplicate detection, and explicit field/form validation. Compute the key only from canonical decimal IDs in `0 <= source_id < 100000`.

```python
def pc_key(source_id: str) -> str:
    if not isinstance(source_id, str) or not source_id.isascii() or not source_id.isdigit():
        raise ValueError("PC source_id must be a decimal string")
    number = int(source_id)
    if str(number) != source_id or not 0 <= number < 100000:
        raise ValueError("PC source_id is outside the canonical reserved range")
    return str(100000 + number)
```

- [ ] Rerun the tests; inspect that the input document remains unchanged after successful merges and failed validation.

## Task 2: Generator, metadata, validator and backswing integration

**Consumes:** Task 1 functions and canonical source contract.
**Produces:** Stable regenerated `cats_data.json` with verified PC units and `pc_catalog`.

- [ ] Add failing fixture-based generator tests in `test_data_generators.py`: run generation twice with a minimal extracted JP DataLocal, names and talent inputs; compare PC blocks and mobile values. Put a deliberately different seed in workspace/data and prove `U/data/inputs/cats_pc.json` wins.
- [ ] Add validator tests in `tests/test_pc_cats_validation.py`: legitimate catalog-only/verified entries pass; forged PC platform on mobile `000`, extra numeric key, corrupt PC measurements, absent seed, wrong counters and incorrect mobile CSV stats fail.
- [ ] Add a backswing test with a PC record `100911` and a valid mobile `911.zip`; assert no bytes are read from that archive and the PC form remains null.

```python
def test_pc_does_not_use_same_number_mobile_archive(self):
    data = {"units": {"100911": {"info": {"platform": "pc", "source_id": "911"},
                                "stats": [[100, 1, 1, 10]]}}}
    missing = populate_backswings(data, self.archives)
    self.assertEqual(data["units"]["100911"]["backswing"], [None])
    self.assertIn("100911/f", missing)
```

Use the archive fixture mechanism already present in `test_cat_backswings.py`.

- [ ] Run the three affected test files separately and confirm failures.
- [ ] Load/validate the canonical seed before generating final output; merge the final data before `prepare_backswings`. Do not change medal/talent preservation or mobile form truncation.

```python
source = load_pc_source(paths.root / "data/inputs/cats_pc.json")
final_data = merge_pc_source(final_data, source)
```

- [ ] Extend validator `validate(..., required_min_forms=None, pc_source=None)`: default source is the repository canonical seed; CLI adds `--pc-source`. Build expected PC blocks with the shared module, compare declared PC data, verify mobile coverage as before, and calculate `total_units = len(units)`.
- [ ] In `populate_backswings`, detect validated PC origin before archive resolution, emit missing-form warnings and set null arrays. Apply the same rule when manifest/version mismatch defers calculations. Never silently skip unknown platform values.
- [ ] Rerun affected tests, then the full unittest suite. Keep public-data verification read-only at this stage.

## Task 3: Sparse-ID loading and platform models in CatStats

**Produces:** App-compatible loading of both legacy mobile-only JSON and the new format.

- [ ] Add failing JVM tests for old JSON defaults, numeric sorting of sparse keys `000,881,100911`, invalid/duplicate numeric keys, and platform/source ID consistency.
- [ ] Add platform metadata to `CatInfo` with mobile defaults; add `pc_forms` to CatData as an optional PC form list and `pc_catalog` to CatsDataResponse with empty-map default.
- [ ] Create serializable `PcCatCatalogEntry`, `PcCatForm`, `PcCatMeasurement`, and `PcCatAbility` matching the shared JSON contract. Preserve null measurements.
- [ ] Create `CatDataEntries.kt` with the testable pure function below. Reject malformed keys rather than sorting them as zero; preserve distinct keys only after canonical validation.

```kotlin
internal fun orderedCatEntries(data: CatsDataResponse): List<Pair<Int, CatData>> =
    data.units.entries.map { (key, unit) ->
        val id = requireNotNull(key.toIntOrNull()) { "Invalid cat ID: $key" }
        require(id >= 0 && key == id.toString().padStart(3, '0'))
        id to unit
    }.sortedBy { it.first }
```

- [ ] Replace the range loop in LocalCatDataSource with iteration over `orderedCatEntries(data)`. Keep current readUnitFromData handling, tags, talent parsing, medals and pre-existing backswing fixes.
- [ ] Carry `platform`, `sourceId`, and `sourceUrl` through CatUnit constructors with backwards-compatible default arguments, so verified PC units retain their identity in UI.
- [ ] Run `gradlew.bat testDebugUnitTest --console=plain` in A; check existing sparse/historical coverage assertions and fix assumptions only where the new contract requires it.

## Task 4: Catalog loading with remote/local fallback

**Consumes:** PcCatCatalogEntry and CatsDataResponse from Task 3.
**Produces:** `CatRepository.pcCatalog: StateFlow<List<PcCatCatalogEntry>>`, exposed by MainViewModel.

- [ ] Add a pure `decodePcCatalog(data: CatsDataResponse): List<PcCatCatalogEntry>` in PcCatCatalog.kt. Validate reserved IDs, source IDs, form codes, finite values, and absence of overlaps with `units`; sort by internal ID.
- [ ] Add JVM tests showing JSON without pc_catalog gives an empty list, malformed remote PC data is rejected, and an explicit valid empty catalog clears the previous catalog while an unsuccessful refresh retains it.
- [ ] Validate the complete candidate response before choosing it as remote success. Treat malformed PC data as a failed remote response, retaining the existing local fallback path and cancellation propagation.
- [ ] Add private `_pcCatalog` MutableStateFlow to CatRepository, publishing decoded entries only after final response and successful cat construction are established. A failure/cancellation before publication leaves prior valid state intact.

```kotlin
private val _pcCatalog = MutableStateFlow<List<PcCatCatalogEntry>>(emptyList())
val pcCatalog: StateFlow<List<PcCatCatalogEntry>> = _pcCatalog.asStateFlow()
```

- [ ] Expose `val pcCatalog = catRepository.pcCatalog` from MainViewModel. Do not put catalog-only entries in `allCats`, comparison lists, recommendation lists or rankings. Keep source selection in the existing single load path; do not fetch a second unrelated response for PC data.
- [ ] Extend repository tests to exercise remote failure, local fallback, a catalog removed by a valid response, and cancellation. Use the project's existing coroutine/cache test fixtures; add injected response decoding helpers if Android context prevents isolated JVM coverage.
- [ ] Run JVM tests and verify all pre-existing repository merge/backswings tests still pass.

## Task 5: PC catalog UI and verified-unit identity

**Produces:** Browsable PC entries by rarity, detail sheet with known fields, and PC identity on verified-unit detail.

- [ ] Add failing tests for display label `PC #911`, rarity grouping, distinct identities for two entries sharing a name, null measurement display and exclusion of catalog-only entries from combat tools.
- [ ] Create `PcCatCatalogSection.kt`: accept entries, selected rarity, favorite IDs and onToggleFavorite; list matching PC entries under «Exclusivos de PC». Use reserved IDs as keys and open a dedicated modal detail sheet on tap.

```kotlin
@Composable
fun PcCatCatalogSection(
    entries: List<PcCatCatalogEntry>,
    selectedRarity: CatType,
    favoriteIds: Set<Int>,
    onToggleFavorite: (Int) -> Unit
)
```

- [ ] In CatsScreen, collect MainViewModel.pcCatalog and render the section in catalog mode, independent of mobile subcategory classification; hide it in recommendations mode. Support browsing forms within the sheet without constructing a Cat instance.
- [ ] The sheet displays name, original ID, acquisition, source link, forms, published measurements with level/treasure context and descriptive abilities. Null/absent values show a localized unavailable label; it has no compare, ranking, talent or animation action. Favorite storage uses the reserved internal ID.
- [ ] Verified CatUnit details display PC label/original ID and preserve descriptive PC abilities; suppress animation access unless there is an explicit verified PC resource capability. Keep normal mobile detail interactions unchanged.
- [ ] Add default and Spanish resource strings for PC origin, incomplete data, unavailable measurement and source. Existing translations fall back through Android resources rather than hardcoded UI text.
- [ ] Add instrumentation tests using fixture entries for rarity browsing, opening both forms, source identity, no fabricated numeric values and absence of animation/compare controls. Run `connectedDebugAndroidTest` when a configured device exists; if absent, report that limitation and run JVM/build verification without claiming instrumentation passed.
- [ ] Run `gradlew.bat testDebugUnitTest assembleDebug --console=plain`; inspect relevant UI on the configured Android surface where available.

## Task 6: Review PC inventory, measurements and images

**Produces:** Canonical reviewed seed, source coverage report, and verified per-form images.

- [ ] Enumerate the wiki's PC-exclusive cat category and review each linked cat page; ignore gacha/enemy/event pages. Include Bun Bun Monger Prototype, Honda Tadakatsu, Type-Monshiro, Momo, New Year Momo, Hatsuyume Mikan, Nuclear Dragon King Berius, Issun Boushi, Entangled Wooden Horse Javelins, Wise Empress Nobel, Battle God Odin, Cat Maid, Neko-Musume Cat, Kitaro Cat & Nezumi-Otoko Cat, Mimiluga, Natsu Mikan and Karasu-Tengu Tenten as inventory candidates, not presumed-ID records.
- [ ] For each candidate, verify source ID, rarity, named forms, acquisition and measurements directly against its page. Preserve source URL and review date. Record inaccessible/unidentified candidates in an execution report outside staging; do not invent IDs or claim complete import.
- [ ] Populate `data/inputs/cats_pc.json` using the shared source contract. Start entries as catalog_only; promote only when every CSV-column interpretation and timing conversion has evidence. Validate the seed with `load_pc_source` before generating any public output.
- [ ] Download verified form photos into the ignored configured image inbox, retaining originals and source-to-form mapping. Name processed public images `uni<internal_id>_<form>00.png`. For evolved c01 originals preserve c01 and add c00 alias. Never rename them to source/mobile ID paths.
- [ ] Use `scripts/tools/actualizar_imagenes.py --source <configured inbox> --kind cats` for processing/export under current tooling. Verify each declared form's image resolves locally; keep existing photos when any download fails. If a form image is unavailable, report it and use the app's missing-image state instead of unrelated artwork.
- [ ] Add a source-contract test loading the real seed and asserting each record's ID, form count and source URL validity. Do not use network in tests.
- [ ] Write `docs/pc-cats.md` covering identity reservation, seed editing, provenance, catalog_only promotion, schema-version meaning, unavailable animations, and old-client compatibility. Update input/architecture docs and verify no personal absolute paths were added.

## Task 7: Coordinated data application and final verification

**Consumes:** Verified app build and canonical source from Tasks 1–6.
**Produces:** Public JSON containing the reviewed PC catalog and a compatible app asset copy.

- [ ] Run read-only preflight in U:

```powershell
.\.venv\Scripts\python.exe check_project.py --game-data
.\.venv\Scripts\python.exe update_all.py --dry-run
```

- [ ] Record selected mobile version and original mobile entries before applying changes. Use `update_all.py --only cats_info evolution animations backswings` to apply only affected data, then inspect outputs and existing medals/talents/localizations. Do not run unrelated names, schedule or event updates.
- [ ] Validate generated JSON with `scripts/tools/validate_cats_data.py`, passing resolved latest JP DataLocal, configured names input and selected version. Review all public PC fields against the canonical seed and compare preserved mobile entries (allow only independently justified derived changes).
- [ ] After app verification, export through the pipeline's `--export-app` for the same affected steps. Inspect app asset changes against its pre-existing diff; do not overwrite unrelated names/talent edits or stage app changes.
- [ ] Extend CatsDataAssetCompatibilityTest to deserialize the real new asset, verify mobile historical coverage/Mushashi medal and assert PC identity/count consistency.
- [ ] Run final mandatory checks in U:

```powershell
.\.venv\Scripts\python.exe update_cat_animations.py --dry-run
.\.venv\Scripts\python.exe update_cat_backswings.py --dry-run
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
```

Require zero changed paths and zero changed units respectively, with warnings
visible. Keep incremental source packs intact.

- [ ] In A, run the configured Python 3.12 against `scripts/tests` fixtures, then `gradlew.bat testDebugUnitTest assembleDebug --console=plain` and `git diff --check`. Do not execute obsolete app data generators as part of validation.
- [ ] Review both final diffs against their original baselines. Report actual imported verified/catalog-only counts, inaccessible candidates/images, test/build results and any unrun device checks. Leave changes uncommitted and unpublished.

## Execution recommendation

Use native execution in this session: the schema, generator and app changes
share interfaces and touch app files with existing edits. Sequential execution
keeps those changes coordinated and avoids multiple workers editing the same
files. Delegated execution remains an option only if the user selects it.

## Resultado de ejecución (2026-10-10)

Se completó la importación de 17 fichas catalog_only y 35 formas/imágenes, la integración de generación/validación y el catálogo en CatStats. Las 882 unidades móviles publicadas se conservaron íntegramente.

Ajustes comprobados durante la ejecución:

- La aplicación final usa update_pc_cats.py y exportación explícita del asset para evitar modificar las cinco discrepancias móviles previas 877–881. La integración del generador habitual se verifica con fixtures.
- La promoción verified se aplaza y se rechaza en productor y consumidor: los cálculos y tiempos PC requieren adaptación adicional. El catálogo descriptivo no fabrica esos valores.
- Los fallos de refresco conservan la última respuesta aceptada; la publicación del catálogo se realiza después del commit de la caché, sin suspensión ni comprobación de cancelación posterior.
- Se ejecutaron pruebas JVM, compilación debug, pruebas Compose en emulador y revisión independiente. No se hizo commit, push ni publicación.

La documentación operativa vigente está en docs/pc-cats.md. Los detalles y logs de ejecución se conservan fuera de staging.
