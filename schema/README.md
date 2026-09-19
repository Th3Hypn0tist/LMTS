# LMTS Database Schema SSOT

This directory is the **single source of truth (SSOT)** for LMTS database structure and database-level ownership boundaries.

## Canonical file

- `LMTS_Database_Schema_v1.sql` — canonical MariaDB/MySQL schema for LMTS shared data, user-owned data, immutable report storage, and rebuildable report indexes.

Do not introduce new database semantics first in installers, service-local SQL, DVS code, or report-server code. Those are consumers/projections of this schema.

The existing `lmts/install/schema_v1.sql` is the currently deployed minimal result-server bootstrap. Until installer/migration wiring is moved to this directory, it is a compatibility/deployment artifact and **not** the semantic source of truth for new database design.

## Ownership model

### Canonical shared data

LMTS owns shared canonical catalogs for:

- hardware identity
- model identity
- test identity/version definitions

Canonical identity always stops at the deepest level known with certainty. Missing identity detail is never guessed.

Shared `unknown` identities are valid canonical buckets when multiple probes resolve to the same known identity level, for example an unresolved RTX 4090 / 24 GB variant.

Manual annotations never change canonical identity.

### User-owned data

Registered users own:

- Systems
- Compute Profiles
- Compositions
- private DVS presets
- invite records they create

Tier-4 is an anonymous Reader state and therefore has no `users` row.

Registered tiers:

- Tier-3 — Registered User
- Tier-2 — Invite-capable; may create/use private DVS presets
- Tier-1 — Canonical Authority; may define/maintain canonical data and approve/publish public DVS presets
- Tier-1337 — Test Authority; defines test content and semantics

Higher authority carries higher accountable scope.

Invite authority is not inherited merely by registration. Progression to Tier-2 is an explicit transition and may be approved by the inviter after eligibility is reached.

### System and Compute Profile

`System` is the automatically probed physical/integrated system.

Users do not manually declare canonical hardware identity. Probe output is normalized and resolved into canonical hardware references.

`Compute Profile` is only a reusable selection of which probed System resources are used for testing.

A report may retain a Compute Profile reference for user-facing provenance, but the report also owns the resolved execution-hardware snapshot. Editing a Compute Profile must never change historical report meaning.

### Model identity

Models use the same canonical-resolution principle as hardware.

Hierarchy:

```text
family
  -> base
    -> branch
      -> provider_model
        -> variant
          -> artifact
```

Provider is part of canonical model identity.

Quantization is part of the canonical model variant.

An exact artifact digest, when available, identifies the artifact level. If it is unavailable, identity stops at the deepest verified level.

Runtime settings such as configured context length, temperature, top-p, seed, thread count and offload settings are report-owned execution configuration, not canonical model identity.

### Compositions

Compositions are user-defined targets, not a global canonical catalog.

Their definition/fingerprint may be snapshotted into reports so later user edits do not change historical benchmark meaning.

### Reports

The immutable LMTS report document remains evidence truth.

The `reports.report_json` payload is not normalized into an alternate SQL truth.

SQL report index tables in this schema are explicitly **derived and rebuildable**. They exist for search, leaderboard and visualization performance only.

They may be dropped and rebuilt from canonical report documents.

## No duplicate truth

The database follows these rules:

1. Canonical hardware/model/test metadata exists once in its catalog.
2. Systems reference canonical hardware.
3. Compute Profiles reference System-local resource instances.
4. Reports carry immutable execution evidence and canonical references.
5. Software/runtime state is report-owned historical snapshot data.
6. Leaderboards, ranks, aggregates and report indexes are derived projections.
7. Public DVS presets are governed publication records; private presets remain user-owned.
8. Authentication data is separate from the public tester profile.

## Probe identity rule

Hardware detection follows:

```text
detect -> normalize -> resolve -> reference
```

Fingerprint/identity keys contain stable component identity only.

Do not include instance- or runtime-varying values such as:

- serial numbers
- PCI bus addresses
- device indexes
- drivers
- CUDA/ROCm versions
- current clocks
- temperature
- utilization
- power state

Deep probed capabilities such as ECC capability, architecture, memory type/capacity, caches and accelerator capabilities belong to canonical component profiles when they describe what the component is or can do.

Execution-time state belongs to the report.

## Schema evolution

The canonical schema is versioned through `lmts_schema_version` using component `database_ssot`.

Schema evolution must preserve:

- immutable historical report meaning
- stable canonical IDs
- stable unknown-bucket meaning
- no ID reuse
- rebuildability of derived indexes

Canonical IDs may be deprecated and replaced, but an existing ID must never be reused to mean another entity.
