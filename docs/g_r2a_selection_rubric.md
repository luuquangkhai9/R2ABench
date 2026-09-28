# G-R2A Candidate Selection Rubric

This document describes the deterministic scoring table used to select G-R2A
candidate repositories before manual inspection. The released score table is:

```text
Dataset/G-R2A/selected_candidates.csv
```

The CSV contains 52 automatically selected candidates. After manual inspection,
one candidate was removed because its architecture diagram could not fully
reflect the repository's functional scope. The final G-R2A release therefore
contains 51 valid samples.

## Selection Summary

| Stage | Count | Description |
| --- | ---: | --- |
| Automatically retained candidates | 52 | Candidates passing the score thresholds and metadata checks. |
| Manually removed candidates | 1 | `s000041_4e10c941` (`CMUChimpsLab/Peekaboo`), removed because the architecture diagram did not fully reflect the repository functionality. |
| Final G-R2A samples | 51 | Candidate folders released under `Dataset/G-R2A/`. |

## Score Dimensions

The total candidate score is the sum of six dimensions:

```text
total_score = effective_doc_score
            + doc_diversity_score
            + requirement_relevance_score
            + temporal_consistency_score
            + traceability_score
            + prd_srs_convertibility_score
```

| Paper symbol | CSV column | Scoring content | Range |
| --- | --- | --- | ---: |
| `S_doc` | `effective_doc_score` | Measures the scale of effective documentation after text cleaning and token estimation. | 0-15 |
| `S_div` | `doc_diversity_score` | Measures evidence-category coverage across functionality, user scenario, API/input-output, deployment, constraints, and non-functional signals. | 0-15 |
| `S_req` | `requirement_relevance_score` | Measures requirement relevance based on covered categories, keyword hits, effective text scale, and functionality/user-scenario signals. | 0-25 |
| `S_time` | `temporal_consistency_score` | Measures temporal consistency between the source snapshot and the architecture view, using statuses such as `resolved_before_view` or `row_sha_with_view_date`. | 0-15 |
| `S_trace` | `traceability_score` | Measures traceability potential based on available documents, source references, document volume, effective text scale, and file-path provenance. | 0-15 |
| `S_srs` | `prd_srs_convertibility_score` | Measures PRD/SRS convertibility based on functionality, constraints, non-functional signals, and sufficient evidence scale. | 0-15 |

## Dimension Rules

The scoring procedure is deterministic and uses only repository metadata and
cleaned repository content statistics. It is designed as a candidate filter,
not as a final quality judgment.

### `S_doc`: Effective Documentation Scale

`effective_doc_score` estimates whether the repository has enough usable text
after cleaning markup, boilerplate, links, and unrelated fragments.

| Condition | Score |
| --- | ---: |
| No usable evidence text | 0 |
| Small but usable evidence corpus | 6 |
| Medium evidence corpus | 11 |
| Large evidence corpus | 15 |

The released candidates have `effective_token_count` from 566 to 186,826 and
`effective_doc_score` from 6 to 15.

### `S_div`: Evidence-Category Diversity

`doc_diversity_score` rewards coverage across the evidence categories used for
SRS reconstruction:

- `functionality`
- `user_scenario`
- `api_io`
- `deployment`
- `constraints`
- `non_functional`

Candidates with broader category coverage receive higher scores. In the
released table, candidates covering all six categories receive 15; candidates
covering five categories receive 12.

### `S_req`: Requirement Relevance

`requirement_relevance_score` measures whether the evidence is likely to
support requirements reconstruction. It uses:

- presence of functionality evidence;
- presence of user-scenario or actor-oriented evidence;
- API/input-output evidence;
- requirement-like keywords and section titles;
- sufficient effective text scale;
- overlap with constraints, deployment, or non-functional signals.

The released candidates all satisfy the requirement-relevance filter and have
`requirement_relevance_score = 25`.

### `S_time`: Temporal Consistency

`temporal_consistency_score` estimates whether the evidence snapshot can be
aligned with the target architecture view.

| `time_resolution_status` | Meaning | Score in released table |
| --- | --- | ---: |
| `resolved_before_view` | A source snapshot before or at the architecture-view date was resolved. | 15 |
| `row_sha_with_view_date` | A row-level source reference exists and the view date is known, but temporal alignment is weaker than a resolved-before-view snapshot. | 11 |
| `row_sha_no_view_date` | A row-level source reference exists, but no view date is available. | 7 |

### `S_trace`: Traceability Potential

`traceability_score` measures whether the candidate has enough provenance to
support evidence-to-requirement traceability. It uses:

- availability of a repository source reference in `source_ref`;
- document fetch status;
- document count;
- effective text scale;
- file-path provenance from collected evidence files;
- diversity of document/source artifact types.

All released candidates have `traceability_score = 15`, indicating that they
have sufficient provenance for evidence-bound SRS construction.

### `S_srs`: PRD/SRS Convertibility

`prd_srs_convertibility_score` estimates whether the collected evidence can be
converted into the normalized SRS schema used by R2ABench. It rewards evidence
that supports:

- functional requirements;
- actor/user-scenario descriptions;
- API or input/output behavior;
- constraints;
- deployment or runtime context;
- non-functional requirements;
- sufficient text scale for a coherent SRS.

In the released table, candidates with strong convertibility receive 15.
Candidates that lack one important signal, such as non-functional evidence, may
receive 13 while still passing the threshold.

## Selection Thresholds

A candidate is automatically retained when it satisfies all of the following:

| Rule | Threshold |
| --- | --- |
| Total score | `total_score >= 85` |
| Requirement relevance | `requirement_relevance_score >= 20` |
| PRD/SRS convertibility | `prd_srs_convertibility_score >= 12` |
| Evidence category coverage | Must include requirement-related evidence, especially functionality and user-scenario/API/input-output signals. |
| Source metadata | Must have a usable repository identifier and source reference when available. |
| Architecture-view metadata | Must have an architecture-view URL or recoverable target view reference. |

The automatic stage intentionally favors recall: it keeps candidates that are
likely to support SRS reconstruction and architecture-reference validation.
Final inclusion still requires manual inspection of the architecture view and
the evidence package.

## Manual Inspection Rule

After automatic scoring, retained candidates are manually inspected. A
candidate is removed if:

- the architecture image is unreadable or not recoverable;
- the architecture view is too partial to represent the repository's functional
  scope;
- the view reflects an unrelated subsystem rather than the target repository;
- the repository evidence cannot support a coherent SRS despite the metadata
  score;
- the source snapshot and target view cannot be reconciled.

The automatically selected candidate `s000041_4e10c941`
(`CMUChimpsLab/Peekaboo`) was removed under this rule because its architecture
diagram could not fully reflect the repository functionality.

## Metadata Columns

`selected_candidates.csv` includes the following metadata fields.

| Column | Description |
| --- | --- |
| `sample_id` | Stable sample identifier used by the dataset. |
| `repository_name` | GitHub repository in `owner/name` form. |
| `image_url` | Original architecture-view URL. |
| `downloadable_url` | Raw/downloadable architecture-view URL when available. |
| `local_image_path` | Construction-time local cache path recorded by the scoring pipeline. This is metadata only and is not required for using the released dataset. |
| `retrieval_strategy` | Evidence retrieval strategy; released candidates use `hybrid`. |
| `total_score` | Sum of the six scoring dimensions. |
| `effective_doc_score` | `S_doc`, documentation scale score. |
| `doc_diversity_score` | `S_div`, evidence-category diversity score. |
| `requirement_relevance_score` | `S_req`, requirement relevance score. |
| `temporal_consistency_score` | `S_time`, temporal consistency score. |
| `traceability_score` | `S_trace`, traceability potential score. |
| `prd_srs_convertibility_score` | `S_srs`, PRD/SRS convertibility score. |
| `effective_token_count` | Estimated usable token count after cleaning. |
| `document_count` | Number of collected evidence documents/fragments used by the scoring stage. |
| `document_type_coverage` | Pipe-separated source artifact types, such as `readme`, `docs`, `config`, `code_api_route`, `schema_model`, `test`, or `deployment_config`. |
| `covered_categories` | Pipe-separated evidence categories used by the scoring dimensions. |
| `source_ref` | Source commit or row-level source reference used for temporal alignment. |
| `view_date` | Timestamp associated with the architecture view when available. |
| `time_resolution_status` | Temporal-alignment status used to compute `S_time`. |
| `document_fetch_status` | Status of evidence document retrieval. |
| `image_download_status` | Status of architecture image download during construction. A failed download does not automatically remove a candidate if the view can still be recovered or validated manually. |
| `notes` | Optional construction notes. |

## Released Score Statistics

The released 52-row candidate table has the following score ranges:

| Column | Min | Max |
| --- | ---: | ---: |
| `total_score` | 86 | 100 |
| `effective_doc_score` | 6 | 15 |
| `doc_diversity_score` | 12 | 15 |
| `requirement_relevance_score` | 25 | 25 |
| `temporal_consistency_score` | 7 | 15 |
| `traceability_score` | 15 | 15 |
| `prd_srs_convertibility_score` | 13 | 15 |
| `effective_token_count` | 566 | 186,826 |
| `document_count` | 1 | 40 |
