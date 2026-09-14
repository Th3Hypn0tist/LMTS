# S3D Data Visualizer Studio (DVS)

DVS is LMTS's generic data-visualization subsystem for turning formal source formats into reusable S3D visualizations without embedding application-specific rendering logic into LMTS or S3D.

Its internal projection boundary has one cell type: **string**. Numeric, categorical, temporal, color and other meanings are declared by visualization interpretation, not stored as alternate table types. This projection is an implementation detail, not a public canonical Input Table contract.

```text
formal source format
    -> Input Template
    -> internal string-row projection
    -> Visualization Preset
    -> recursive visual generations
    -> generic visual plan
    -> S3D visual representation
```

## Feature baseline

| Capability | Baseline |
| --- | --- |
| Input Template model | Complete |
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

An Input Template defines how a formalized source format becomes rows, columns and string cells for the internal DVS projection boundary.

It declares:

- `source_format`
- reader
- row selector
- named columns
- selector for each column

Selectors are strict. Missing fields are errors. There is no `on_missing` fallback semantics.

If unavailable data is valid for a source format, the source format must represent it explicitly. `lmts.report/1.1` represents unavailable known measurements with JSON `null`; DVS then projects that actual source value to the string `"null"`.

The LMTS report template is:

```text
lmts/dvs/templates/lmts-report-v1.1.json
```

It reads the canonical `lmts.report/1.1` interchange document used by disk export, the result server and DVS. DVS does not maintain a parallel LMTS report model.

## Visualization Presets

A Visualization Preset defines how projected columns become visual structure.

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

Application-specific meaning belongs here, not in DVS core. The first LMTS-specific preset is:

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

`project_visualization()` applies an Input Template and Visualization Preset to source data and emits a generic `s3d.dvs.visual-plan/1.0` document. It contains only primitive, visibility, visual-channel, grouping and source-row information. It does not contain LMTS-specific renderer logic.

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

Studio is the authoring and validation surface. Its intended complete feature set is:

- create, edit and inspect Input Templates
- create, edit and inspect Visualization Presets
- choose source format
- preview source -> internal projection
- inspect projected columns and values
- create recursive generation hierarchies
- choose visual primitive per generation
- bind columns to visual channels
- configure interpretation and transforms
- validate preset <-> template compatibility
- reject unknown columns and invalid definitions
- load/save reusable templates and presets
- manage registered definitions
- preview the same visualization consumed by Visualizer

Studio is owned by the Python DVS host.

## Visualizer

**Feature baseline: complete.**

Visualizer is the read/inspection surface. It consumes a generic visual plan recursively and renders through S3D. Current packed bridge support materializes `box` primitives and maps generic channels into S3D packed box instances.

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
POST /api/extract
POST /api/visualize
```

`POST /api/extract` accepts exactly `input_template_id` and `source` and returns the projected `columns` and `rows`. There is deliberately no `/api/table` compatibility alias: the internal projection is not a public Input Table model.

`POST /api/visualize` accepts exactly `input_template_id`, `visualization_preset_id` and `source`, validates template/preset compatibility and returns the generic visual plan consumed by the visualization layer.

The viewer-facing API is read-oriented. Studio mutation endpoints belong only to the Python host and may evolve without changing the shared Input Template or Visualization Preset formats.

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
2. Source formats own missing-value semantics.
3. The string projection is an internal transport/runtime boundary, not an application data model.
4. Visualization semantics belong to Visualization Presets.
5. Input Templates know source structure, not application meaning.
6. Studio and Visualizer consume the same canonical definitions.
7. S3D owns generic 3D mechanics and packed layout; DVS does not build a parallel renderer or face-order truth.
8. High-density visualization stays packed instead of creating one SceneObject per observation.
9. Python Studio semantics are not duplicated in viewer-only hosts.
10. DVS consumes `lmts.report/1.1` directly; it does not create a second LMTS report format.
11. Visual plans are generic renderer input, not a second application-data authority.
12. Per-face channels are all-or-nothing; there is no partial-color fallback semantics.
