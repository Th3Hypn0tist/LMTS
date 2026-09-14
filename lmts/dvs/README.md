# S3D Data Visualizer Studio (DVS)

DVS is a generic data-visualization subsystem embedded in LMTS.

Its canonical input model has one cell type: string. Numeric, categorical, temporal, color and other meanings are interpretations declared by a Visualization Preset, not intrinsic data types.

```text
source format
    -> Input Template
    -> generic string table
    -> Visualization Preset
    -> S3D visual representation
```

An Input Template defines how a formalized source format is read as rows, columns and string cells. A Visualization Preset binds those columns to explicit visual primitives and channels. Generations are recursive, and each generation declares its own primitive and bindings.

Host roles are intentionally asymmetric:

```text
Python DVS host = Studio + Viewer
PHP DVS host    = Viewer only
```

The PHP host must consume the same Input Templates and Visualization Presets as the Python host. It does not implement preset/template authoring semantics.

The Python server is stdlib-only and follows the Structure-style `ThreadingHTTPServer` pattern. The shared viewer API is read-only. Studio mutation endpoints, when added, belong only to the Python host.
