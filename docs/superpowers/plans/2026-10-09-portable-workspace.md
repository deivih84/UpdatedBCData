# Portable workspace implementation plan

> For agentic workers: execute inline using superpowers:executing-plans. The user approved the design and requested execution. Keep changes reviewable in the requested repository; do not commit, push or alter external originals.

**Goal:** Reproduce UpdatedBCData maintenance on Windows and Linux from Git.

**Architecture:** Repository-root path resolution, local configuration overrides, imported data generators, versioned seed inputs and optional app export. Preserve current public paths and modern entrypoints.

**Tech stack:** Python 3.12, unittest, pathlib, existing synchronizer dependencies plus pandas/cloudscraper/lxml for imported tools.

**Spec:** `docs/superpowers/specs/2026-10-09-portable-workspace-design.md`

## Global constraints

- Preserve existing uncommitted cats_data.json, data_version.json and backswing work.
- EN/JP stay separate; incremental animation merge remains mandatory.
- Add backswings immediately after animations, including animation-only repair.
- Keep external source copies intact and publication URLs unchanged.
- Store credentials, APK sources, virtualenvs and local paths outside tracked configuration.

## Review focus

- Invocation outside the repo or under a path with spaces.
- Explicit invalid local paths must not select a different checkout silently.
- Clean clone without CatStats or BCData must import scripts and run fixture tests.
- Failed pipeline must not advance metadata, export or push.
- Curated combo and talent seeds must survive migration and new-machine setup.

### Task 1: Paths and diagnosis

**Files:** workspace_paths.py, workspace.example.json, check_project.py, tests/test_workspace_paths.py.
**Produces:** Workspace.load(root=None, overrides=None, environ=None), latest_version_dir(root, region), drawable_path(repo, explicit=None, configured=None).

- [x] Write tests for repository-relative resolution, precedence, absent app, invalid override and semantic versions.
- [x] Run `python -m unittest discover -s tests -p test_workspace_paths.py -v`; expect missing module failure.
- [x] Implement resolver and non-mutating diagnostics; run the same tests, expect pass.

### Task 2: Imported sources and seed inputs

**Files:** scripts/data, scripts/tools, scripts/legacy, data/inputs, tests/test_data_generators.py, docs/migration-inventory.md.
**Consumes:** Workspace and semantic version resolver.
**Produces:** Import-safe generators writing to workspace/data and public repository outputs.

- [x] Write import/seed/semantic-version tests before copying/adapting sources. Expect missing modules.
- [x] Copy the audited tools and their direct dependencies; adapt paths and failure reporting; keep external originals.
- [x] Copy curated inputs and protected state; make standalone commands prepare working copies explicitly.
- [x] Run fixture tests and CLI help from another directory; expect no writes on import/help.

### Task 3: Orchestrator and export

**Files:** update_all.py, tests/test_update_all.py.
**Consumes:** Imported script paths and Workspace.
**Produces:** Validated step selection, fail-fast execution, explicit app export and optional scoped push.

- [x] Write tests for unknown steps, animation dependency, failure preventing metadata/export/push and subprocess environment forwarding. Expect missing module.
- [x] Implement argparse pipeline with preflight and per-step requirements; preserve animation-only timestamps.
- [x] Run `python -m unittest discover -s tests -p test_update_all.py -v`; expect pass.

### Task 4: Existing updater integration

**Files:** sync_gacha_catalog.py, event_updater.py, bc_event_name_resolver.py, update_cat_animations.py, sync configs, maintenance utilities.
**Consumes:** Shared path resolver; retain explicit CLI precedence.

- [x] Cover configured drawables on Linux, repository overrides and invalid source overrides.
- [x] Remove personal shared paths, connect BCData and app lookup, anchor relative file access.
- [x] Run the full unittest suite; expect all fixture tests pass.

### Task 5: Reproduction and agent documentation

**Files:** README.md, AGENTS.md, CLAUDE.md, docs/workspace.md, docs/architecture.md, requirements.txt, requirements-legacy.txt, .gitignore, CI workflow.

- [x] Document installation and configuration in PowerShell and Linux shell, required game sources and optional export.
- [x] Preserve operational contracts, remove absent commands, label historical plans, record migration provenance.
- [x] Install dependencies in a fresh venv; run tests and CLI diagnostics in a fresh copied tree without local configuration or sibling projects.
- [x] Run animation and backswing dry-runs, retaining warnings; require zero pending changes.
- [x] Obtain a fresh reviewer, resolve significant findings, inspect diff and git diff --check.

## Execution record

- Baseline: 148 tests pass (existing backswing additions included).
- Execution remains in the requested checkout. No commits or worktree migration; this keeps the user's uncommitted changes and final review in one place.

- Tasks 1–5: complete. Final suite: 183 tests; clean tree: 1622 files; all modern/imported CLI help from an external cwd passed without writes.
- Review: two significant findings reproduced RED→GREEN (summary metadata rollback and shared stage source selection); full suite green afterward.
- Animation dry-run: zero changed paths. Backswing dry-run: zero changed units; 56 unavailable forms retain warnings.
- Windows runtime validated; Linux dependency wheels resolved and CI prepared, runtime validation remains pending CI.
