# S3D Data Visualizer Studio (DVS)

DVS is LMTS's generic data-visualization subsystem for turning formal source formats into reusable S3D visualizations without embedding application-specific rendering logic into LMTS or S3D.

Its canonical table boundary has one cell type: **string**. Numeric, categorical, temporal, color and other meanings are declared by visualization interpretation, not stored as alternate table types.

```text
formal source format
    -> Input Template
    -> strict generic string table
    -> Visualization Preset
    -> recursive visual generations
    -> S3D visual representation
```

## Feature baseline

| Capability | Baseline |
| --- | --- |
| Input Template model | Complete |
| Visualization Preset model | Complete |
| Registry and validation | Complete |
| Strict missing-field semantics | Complete |
| Python DVS host | Complete baseline |
| Studio | Complete feature baseline |
| Visualizer | Complete feature baseline |
| S3D packed visualization integration | Complete baseline |
| PHP viewer | Portability target |
| Per-face packed visual channels | Later extension |

## Input Templates

An Input Template defines how a formalized source format becomes rows, columns and string cells.

It declares:

- `source_format`
- reader
- row selector
- named columns
- selector for each column

Selectors are strict. Missing fields are errors. There is no `on_missing` fallback semantics.

If unavailable data is valid for a source format, the source format must represent it explicitly. For example, `lmts.report/1.0` represents unavailable standard measurements with JSON `null`; DVS then projects that actual source value to the string `"null"`.

## Visualization Presets

A Visualization Preset defines how table columns become visual structure.

It declares:

- source-format compatibility
- Input Template reference
- recursive visual generations
- primitive per generation
- optional grouping
- named visual-channel bindings
- interpretation metadata
- transform metadata

Every binding must reference an actual Input Template column. Recursive child generation IDs are validated and duplicate IDs are rejected.

## Studio

**Feature baseline: complete.**

Studio is the authoring and validation surface. Its intended complete feature set is:

- create Input Templates
- edit Input Templates
- inspect Input Templates
- create Visualization Presets
- edit Visualization Presets
- inspect Visualization Presets
- choose source format
- preview source → table projection
- inspect projected columns and values
- create recursive generation hierarchies
- choose visual primitive per generation
- bind columns to visual channels
- configure interpretation and transforms
- validate preset ↔ template compatibility
- reject unknown columns and invalid definitions
- load/save reusable templates and presets
- manage registered definitions
- preview the same visualization consumed by Visualizer

Studio is owned by the Python DVS host.

## Visualizer

**Feature baseline: complete.**

Visualizer is the read/inspection surface. Its intended complete feature set is:

- load formal source data
- choose a compatible Input Template
- project source data through the strict string-table boundary
- choose a compatible Visualization Preset
- generate recursive visual structures
- render through S3D
- use packed high-density rendering for observation-heavy visualizations
- map dimensions independently to position, rotation, scale and RGB channels
- navigate the 3D scene
- select and inspect rendered data
- reuse visualization definitions without application-specific renderer code

Visualizer never becomes a new source of truth. It consumes source data and reusable visualization definitions.

## Host roles

```text
Python DVS host = Studio + Visualizer
PHP DVS host    = Visualizer portability target
```

The PHP host must consume the same Input Templates and Visualization Presets as the Python host. It does not implement independent authoring semantics.

## Python host

The Python host is stdlib-only and follows the Structure-style `ThreadingHTTPServer` pattern.

Current host API surfaces include:

```text
GET  /api/health
GET  /api/input-templates
GET  /api/input-templates/<id>
GET  /api/visualization-presets
GET  /api/visualization-presets/<id>
POST /api/table
```

The viewer-facing API is read-oriented. Studio mutation endpoints belong only to the Python host and may evolve without changing the shared Input Template or Visualization Preset formats.

## S3D visual channels

The current Statistics-domain visual encoding model supports independent numeric dimension mapping to:

```text
position.x
position.y
position.z
rotation.x
rotation.y
rotation.z
scale.x
scale.y
scale.z
color.r
color.g
color.b
```

Packed box instances currently use 13 floats:

```text
position XYZ   3
scale XYZ      3
rotation XYZ   3
RGB            3
alpha          1
----------------
total         13
```

Alpha currently remains a render/batch property. Per-face channels are the next packed-model extension.

## Architectural rules

1. DVS does not invent missing source data.
2. Source formats own missing-value semantics.
3. The string table is a transport boundary, not an application data model.
4. Visualization semantics belong to Visualization Presets.
5. Input Templates know source structure, not application meaning.
6. Studio and Visualizer consume the same canonical definitions.
7. S3D owns generic 3D mechanics; DVS does not build a parallel renderer.
8. High-density visualization stays packed instead of creating one SceneObject per observation.
9. Python Studio semantics are not duplicated in viewer-only hosts.
