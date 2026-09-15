# S3D Data Visualizer Studio (DVS)

DVS is LMTS's generic data-visualization subsystem for turning formal source formats into reusable S3D visualizations without embedding application-specific rendering logic into LMTS or S3D.

The Input Template owns source extraction and basic typing. The current canonical Input Column types are:

```text
string
number
boolean
```

`number` means any finite numeric value. Numeric strings are parsed to numbers by the Input Template. `null` is not a type; nullable source values are declared separately with `nullable: true`.

```text
formal source format
    -> Input Template selector
    -> Input Template type
    -> optional Input Template scale
    -> typed input projection
    -> Visualization Preset
    -> recursive visual generations
    -> generic visual plan
    -> S3D visual representation
```

## Feature baseline

| Capability | Baseline |
| --- | --- |
| Input Template model | Complete |
| Typed Input Columns | `string`, `number`, `boolean` |
| Input scaling | `low`, `high`, `power` + typed range scan |
| Visualization Preset model | Complete |
| Registry and validation | Complete |
| Strict missing-field semantics | Complete |
| Recursive visual-plan runtime | Complete baseline |
| Python DVS host | Complete baseline |
| Studio | Complete feature baseline |
| Visualizer | Complete feature baseline |
| LMTS report Input Template | `lmts.report/1.1` |
| LMTS benchmark preset | `lmts.benchmark.landscape.v1` |
| S3D packed visualization integration | Complete baseline |
| Per-face packed RGBA channels | Complete baseline |
| PHP viewer | Portability target |

## Input Templates

An Input Template defines how a formalized source format becomes a typed internal DVS projection.

It declares:

- `source_format`
- reader
- row selector
- named columns
- selector for each column
- type for each column
- optional `nullable: true`
- optional numeric `scale`

Example:

```json
{
  "name": "wind_speed",
  "selector": "wind_speed",
  "type": "number",
  "scale": {
    "low": 0.2,
    "high": 5.9,
    "power": 1.0
  }
}
```

Selectors and types are strict. Missing fields are errors. There is no `on_missing` fallback semantics. A scale is valid only for a `number` column.

Typing happens before scaling. For a numeric column, the scale is:

```text
output = ((input - low) / (high - low)) ^ power
```

There is no implicit clamp. `high` must be greater than `low`, `power` must be greater than zero, and all scale values must be finite.

Studio can scan the selected numeric column with **Find lowest** and **Find highest**. The scan uses the Input Template selector and type conversion, but runs before scaling. Accepted nullable `null` values are skipped for range calculation. If no numeric values remain, the scan fails rather than inventing a range.

The scale is not discarded after projection. Each scaled column exposes one canonical input parameter:

```text
scale.<column>
```

For example:

```text
scale.wind_speed = { low: 0.2, high: 5.9, power: 1.0 }
```

Visualization generations can bind that complete object as a parameter:

```json
"parameters": {
  "scale": "scale.wind_speed"
}
```

The same scale definition can therefore drive both value calibration and visual representations such as an axis, legend or scale display without duplicate truth.

If unavailable data is valid for a source format, the source format must represent it explicitly. `lmts.report/1.1` represents unavailable known measurements with JSON `null`; nullable Input Columns preserve that as an actual typed `null`/`None` value. Null is never represented by the string `"null"` unless the source column is explicitly typed as a string containing that text.

The LMTS report template is:

```text
lmts/dvs/templates/lmts-report-v1.1.json
```

It reads the canonical `lmts.report/1.1` interchange document used by disk export, the result server and DVS. DVS does not maintain a parallel LMTS report model.

## Visualization Presets

A Visualization Preset defines how typed projected columns become visual structure.

It declares:

- source-format compatibility
- Input Template reference
- recursive visual generations
- primitive per generation
- optional grouping
- named visual-channel bindings
- optional input-parameter bindings
- interpretation metadata
- transform metadata

Every channel binding must reference an actual Input Template column. Every parameter binding must reference an actual Input Template parameter. Recursive child generation IDs are validated and duplicate IDs are rejected.

The Visualization Preset does **not** own basic source typing. It receives values already typed by the Input Template. Its interpretations describe visual use, not conversion from arbitrary source strings into application types.

Application-specific visual meaning belongs here, not in DVS core. The first LMTS-specific preset is:

```text
lmts.benchmark.landscape.v1
```

Its current definition uses:

```text
target         -> position.x categorical index
test           -> position.z categorical index
score_percent  -> position.y + scale.y
result         -> uniform RGB channels
```

The first LMTS preset deliberately remains uniform RGB. S3D and DVS support per-face RGBA, but the benchmark preset will not assign invented meaning to individual faces before useful benchmark semantics exist.

This establishes the first real `LMTS Benchmark Report -> Input Template -> Visualization Preset` chain while keeping DVS and S3D generic. The preset may evolve as LMTS discovers which benchmark metrics distinguish models, bots and compositions most usefully. It is not the future locked AIGM LM Benchmark Report profile.

## Generic visual plan

`project_visualization()` applies an Input Template and Visualization Preset to source data and emits a generic `s3d.dvs.visual-plan/1.0` document. It contains primitive, visibility, typed visual-channel, parameter-binding, grouping and source-row information. It does not contain LMTS-specific renderer logic.

Input parameters are exposed at the visual-plan root. A generation that binds an input parameter receives the same value under its local parameter name.

Current generic interpretations are:

```text
categorical-index
number
number-or-null
category-channel
```

Transforms are strict. Unsupported transform fields fail. There is no implicit aggregation inside a generation group: if a binding resolves to several different source values, projection fails instead of guessing an aggregate.

For `number-or-null`, an explicit `null: "not-rendered"` transform marks that visual group `visible: false`. DVS does not manufacture a replacement value.

Recursive child generations are projected using only their parent group's row subset. `source_rows` remains expressed in the original Input Template row index space at every recursion depth. This behavior is regression-tested through a three-level generation tree.

## Studio

**Feature baseline: complete.**

Studio is the authoring and validation surface. Its current feature set includes:

- create, edit and inspect Input Templates
- create, edit and inspect Visualization Presets
- choose source format
- define Input Column type and nullability
- define numeric Input Scales
- find typed pre-scale low/high values from source data
- preview source -> typed projection
- inspect projected columns, types, values and input parameters
- create recursive generation hierarchies through the canonical definition contract
- choose visual primitive per generation
- bind columns to visual channels
- bind Input Template parameters to generations
- configure interpretation and transforms
- validate preset <-> template compatibility
- reject unknown columns, parameters and invalid definitions
- load/save reusable templates and presets
- manage registered definitions
- preview the same visualization consumed by Visualizer

The current browser Studio is a canonical contract editor with focused scale controls. Validate and Preview never persist. Create and Update are explicit persisted operations.

System definitions are read-only. Studio-authored definitions live under the local Studio root and cannot shadow system definitions with the same ID.

Studio is owned by the Python DVS host.

## Visualizer

**Feature baseline: complete.**

Visualizer is the read/inspection surface. It consumes a generic visual plan recursively and renders through S3D. Current packed bridge support materializes `box` primitives and maps generic channels into S3D packed box instances. `group` is a structural generation primitive: it recurses into children but does not materialize geometry or affect camera bounds.

Visualizer never becomes a new source of truth. It consumes source data and reusable visualization definitions.

## Host roles

```text
Python DVS host = Studio + Visualizer
PHP DVS host    = Visualizer portability target
```

The PHP host must consume the same Input Templates and Visualization Presets as the Python host. It does not implement independent authoring semantics.

## Python host

The Python host is stdlib-only and follows the Structure-style `ThreadingHTTPServer` pattern.

Current read/runtime API surfaces include:

```text
GET  /api/health
GET  /api/input-templates
GET  /api/input-templates/<id>
GET  /api/visualization-presets
GET  /api/visualization-presets/<id>
POST /api/extract
POST /api/visualize
```

Studio API surfaces include:

```text
POST /api/studio/validate/input-template
POST /api/studio/preview/input-template
POST /api/studio/range/input-template
POST /api/studio/validate/visualization-preset
POST /api/studio/preview/visualization-preset
POST /api/studio/input-templates
PUT  /api/studio/input-templates/<id>
POST /api/studio/visualization-presets
PUT  /api/studio/visualization-presets/<id>
```

`POST /api/extract` accepts exactly `input_template_id` and `source` and returns the projected `columns`, `column_types`, typed `rows` and `parameters`. There is deliberately no `/api/table` compatibility alias.

`POST /api/studio/range/input-template` accepts exactly `definition`, `source` and `column`. It parses the draft Input Template, scans that numeric column through its selector and type conversion before scaling, and returns `low` and `high` without persisting anything.

`POST /api/visualize` accepts exactly `input_template_id`, `visualization_preset_id` and `source`, validates template/preset compatibility and returns the generic visual plan consumed by the visualization layer.

## S3D visual channels

The uniform box bridge accepts:

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
color.a
```

S3D owns the canonical packed box representation. It currently uses 33 floats:

```text
position XYZ                    3
scale XYZ                       3
rotation XYZ                    3
face z- RGBA                    4
face z+ RGBA                    4
face x- RGBA                    4
face x+ RGBA                    4
face y- RGBA                    4
face y+ RGBA                    4
---------------------------------
total                          33 floats / instance
```

The canonical face order belongs to S3D:

```text
z-, z+, x-, x+, y-, y+
```

DVS does not duplicate that order as application truth. The visualizer reads `S3D.BOX_FACE_ORDER` from the loaded S3D core.

Generic per-face channels use:

```text
face.<S3D-face-id>.color.r
face.<S3D-face-id>.color.g
face.<S3D-face-id>.color.b
face.<S3D-face-id>.color.a
```

Per-face semantics are strict. If any per-face color channel is present, the complete `6 x RGBA` set is required in the face set defined by S3D. Partial face definitions, unknown face IDs and missing S3D face-order metadata are errors. DVS does not fall back to uniform color to fill missing face values.

If no per-face channels are present, the visualizer uses the uniform `color.*` path. S3D replicates that one RGBA value into all six canonical face slots; there is no separate base-color plus override truth.

The S3D Statistics-domain `VisualEncoding` currently exposes RGB channels. That domain contract is separate from the more general DVS -> S3D box bridge, which supports uniform alpha and strict per-face RGBA.

## Architectural rules

1. DVS does not invent missing source data.
2. Source formats own whether missing/unavailable values are representable; Input Templates own whether a selected column accepts `null`.
3. Input Templates own extraction, basic typing and optional numeric scaling.
4. The canonical Input Column types are `string`, `number` and `boolean`; `null` is an accepted value, not a type.
5. Range discovery uses typed values before scaling.
6. Input scales are exposed downstream as one `scale.<column>` parameter object so calibration and visual scale representation share one truth.
7. Visualization semantics belong to Visualization Presets.
8. Studio and Visualizer consume the same canonical definitions.
9. S3D owns generic 3D mechanics and packed layout; DVS does not build a parallel renderer or face-order truth.
10. High-density visualization stays packed instead of creating one SceneObject per observation.
11. Python Studio semantics are not duplicated in viewer-only hosts.
12. DVS consumes `lmts.report/1.1` directly; it does not create a second LMTS report format.
13. Visual plans are generic renderer input, not a second application-data authority.
14. Per-face channels are all-or-nothing; there is no partial-color fallback semantics.
