# G-R2A Evidence Retrieval Settings

This document records the full evidence-retrieval settings used during G-R2A
SRS construction. The released strategy is recorded as `hybrid` in
`Dataset/G-R2A/selected_candidates.csv` and in each sample-level
`evidence_pack.json`.

## Retrieval Scope

G-R2A retrieves evidence from cleaned repository artifact chunks. When temporal
metadata is available, the source snapshot is aligned with the architecture
view timestamp before evidence is collected.

| Setting | Released value |
| --- | --- |
| Retrieval strategy | `hybrid` |
| Artifact types | `readme`, `docs`, `requirements_like`, `tutorial_guide`, `release_notes`, `code_api_route`, `code_cli`, `schema_model`, `test`, `config`, `deployment_config` |
| Evidence categories | `functionality`, `user_scenario`, `api_io`, `deployment`, `constraints`, `non_functional` |
| Section queries | `functional_requirements`, `non_functional_requirements`, `constraints`, `external_interfaces`, `data_requirements` |
| Selected evidence per sample | 6 evidence chunks after section-aware selection and deduplication |

## Fusion Formula

For each SRS section `s`, the retrieval stage computes three ranked lists over
the same candidate chunks and fuses them with weighted reciprocal-rank fusion:

```text
RRF_s(c) = sum_{r in {BM25, VSM, code}} w_r / (k + rank_{r,s}(c))
```

where `c` is a candidate chunk, `rank_{r,s}(c)` is the 1-based rank of that
chunk under retrieval signal `r` for section `s`, and `k` is the RRF smoothing
constant. Only retrieval signals that return a chunk contribute to its fused
score.

| Parameter | Value |
| --- | ---: |
| `w_BM25` | 1.0 |
| `w_vsm` | 0.9 |
| `w_code` | 0.8 |
| `k` | 60 |

## Retrieval Signals

| Signal | Purpose | Ranking rule |
| --- | --- | --- |
| BM25 lexical retrieval | Prefer chunks that directly match section query terms, requirement words, and architecture identifiers. | Rank cleaned chunks by BM25-style lexical relevance. |
| VSM cosine retrieval | Add a lightweight semantic signal without relying on external embedding services. | Rank chunks by token-frequency cosine similarity after query/chunk token expansion with a predefined equivalence table. |
| Code-aware retrieval | Recover architecture-relevant evidence from source files when documentation is incomplete. | Rank chunks with section-specific path and file-type priors. |

## Code-Aware Priors

The code-aware branch uses conservative path and file-type priors.

| SRS section | Higher-priority evidence |
| --- | --- |
| `functional_requirements` | README/docs, tests, CLI entry points, API routes, controllers, services, and feature-oriented code. |
| `external_interfaces` | API routes, protocol/interface definitions, CLI commands, integration code, and documented input/output behavior. |
| `data_requirements` | Schema/model files, database-related configuration, serialization code, tests, and data-shape documentation. |
| `constraints` | Dependency/configuration files, build files, deployment files, environment files, and technology-stack documentation. |
| `non_functional_requirements` | Deployment/configuration files, reliability/security/performance-related documentation, tests, release notes, and operational guidance. |

## Released Trace Fields

The evidence packs expose retrieval provenance through these fields:

| Field | Meaning |
| --- | --- |
| `features.retrieval_strategy` | Overall strategy name; released G-R2A samples use `hybrid`. |
| `features.retrieval_sections` | SRS sections queried during evidence retrieval. |
| `evidence_chunks[].section` | Section query that selected the evidence chunk. |
| `evidence_chunks[].retrievers` | Retrieval branches that returned the chunk, for example `bm25|code|dense|hyde`. The `dense` label corresponds to the VSM/cosine branch in the released construction metadata; `hyde` marks fixed query-expansion hits used during candidate collection. |
| `evidence_chunks[].score` | Final fused retrieval score used for ranking the selected evidence chunk. |
| `evidence_chunks[].path` and `evidence_chunks[].doc_type` | Repository-relative provenance and coarse artifact type for traceability. |
