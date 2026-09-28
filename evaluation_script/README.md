# R2ABench Evaluation Scripts

This directory contains the evaluation utilities for R2ABench
requirements-to-architecture (R2A) experiments. The scripts evaluate generated
PlantUML architecture diagrams against reference architecture diagrams and
software requirements documents.

The framework has three main evaluation layers:

- L0 checks whether a generated PlantUML diagram can be rendered and parsed.
- L1 computes structural correspondence against a reference architecture.
- L2 uses an OpenAI-compatible judge to assess requirement-grounded semantic
  quality.

It also includes review utilities for building portable JSON review samples and
comparing collected human judgments with model-judge scores.

## Directory Overview

```text
evaluation_script/
  __init__.py                  # Package marker for python -m execution
  evaluate.py                  # Batch evaluation entry point
  pipeline.py                  # File discovery, dataset indexing, CSV output
  l0_syntax.py                 # L0 PlantUML renderability and parse checks
  l1_structural.py             # L1 structural metrics and node alignment
  l2_semantic.py               # L2 LLM-based semantic judge
  plantuml_parser.py           # Conservative PlantUML component parser
  prepare_review.py            # Build portable JSON review samples
  compare_human.py             # Compare human reviews with model scores
  README.md                    # This documentation
```

Expected repository-level inputs and outputs:

```text
Dataset/
  G-R2A/
  E-R2A/
Output/
  G-R2A/
  E-R2A/
  results_g_r2a.csv
  results_e_r2a.csv
```

## Environment

Run commands from the repository root:

```powershell
python -m evaluation_script.evaluate --help
```

Recommended baseline:

- Python 3.10 or newer.
- PlantUML available either on `PATH`, through `PLANTUML_CMD`, or through
  `PLANTUML_JAR`.
- Optional: an OpenAI-compatible API endpoint if L1/L2 judge calls are enabled.

Configure PlantUML with one of the following approaches:

```powershell
# Option 1: plantuml is already on PATH
plantuml -version

# Option 2: explicit Java command
$env:PLANTUML_CMD='java -jar "<path-to-plantuml.jar>"'

# Option 3: jar path only
$env:PLANTUML_JAR="<path-to-plantuml.jar>"

# Optional render timeout in seconds
$env:PLANTUML_TIMEOUT_SECONDS="60"
```

Configure an LLM judge only when needed:

```powershell
$env:OPENAI_API_KEY="<your-api-key>"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="<judge-model-name>"
```

Never commit real API keys or private service credentials. Prefer environment
variables or your CI/CD secret store.

## Quick Start

Evaluate G-R2A predictions:

```powershell
python -m evaluation_script.evaluate `
  --pred .\Output\G-R2A `
  --dataset-dir .\Dataset\G-R2A `
  --out .\Output\results_g_r2a.csv
```

Evaluate E-R2A predictions:

```powershell
python -m evaluation_script.evaluate `
  --pred .\Output\E-R2A `
  --dataset-dir .\Dataset\E-R2A `
  --out .\Output\results_e_r2a.csv
```

The commands above run L0 and any L1 work that can use existing reference data
and cached alignments. To call a judge for missing L1 node alignments, add:

```powershell
  --enable-l1-judge `
  --l1-judge-model <judge-model-name>
```

To enable L2 semantic judging, add:

```powershell
  --enable-l2-judge `
  --llm-model <judge-model-name>
```

Example with both judge layers enabled:

```powershell
python -m evaluation_script.evaluate `
  --pred .\Output\G-R2A `
  --dataset-dir .\Dataset\G-R2A `
  --enable-l1-judge `
  --l1-judge-model <alignment-judge-model> `
  --enable-l2-judge `
  --llm-model <semantic-judge-model> `
  --out .\Output\results_g_r2a.csv
```

## Batch Entry Point

Main command:

```powershell
python -m evaluation_script.evaluate [options]
```

Common options:

| Option | Description |
| --- | --- |
| `--pred` | Generated PlantUML file or directory. |
| `--pred-dir` | Alias for `--pred`. |
| `--pred-root` | Metadata root used to infer workflow, model, and sample IDs when evaluating a subdirectory. |
| `--dataset-dir` | Dataset root containing project/sample folders with reference diagrams and requirement files. |
| `--gt-dir` | Optional standalone reference diagram directory. |
| `--requirements-dir` | Optional standalone requirements/SRS directory. |
| `--out` | Output CSV path. Default: `evaluation/results.csv`. |
| `--resume-from` | Reuse rows from an existing CSV when candidate and sample match a previous successful L0 row. |
| `--only-resume-rows` | With `--resume-from`, evaluate only candidate/sample keys already present in the resume CSV. |
| `--enable-l1-judge` | Call an OpenAI-compatible judge for L1 semantic node alignment if no cache is available. |
| `--l1-judge-model` | Model name for L1 node alignment. Defaults to `--llm-model` if omitted. |
| `--enable-l2-judge` | Call an OpenAI-compatible judge for L2 semantic evaluation. |
| `--llm-model` | Model name for L2 semantic judging. |
| `--llm-base-url` | OpenAI-compatible API base URL. |
| `--llm-api-key-env` | Environment variable containing the API key. Default: `OPENAI_API_KEY`. |

Batch evaluation writes a checkpoint to `--out` after each sample, so completed
rows remain available if a long run is interrupted.

## Input Matching

`evaluate.py` discovers files with these extensions:

- `.puml`
- `.plantuml`
- `.wsd`

It can evaluate either a single file or a directory tree.

Prediction metadata is inferred from the path relative to `--pred` or
`--pred-root`. For example:

```text
Output/G-R2A/direct/gpt-5/s000001_3c90b51c/predicted.puml
```

With `--pred .\Output\G-R2A`, the inferred metadata is:

```text
workflow     = direct
model_id     = gpt-5
sample_id    = s000001_3c90b51c
candidate_id = direct/gpt-5
```

Generic prediction filenames such as `predicted.puml`, `prediction.puml`,
`candidate.puml`, `output.puml`, `generated.puml`, and `architecture.puml`
cause the parent directory name to be used as the sample ID.

## Dataset Layout

The dataset indexer supports both direct sample folders and language-grouped
project folders.

Direct sample layout:

```text
Dataset/G-R2A/
  s000001_3c90b51c/
    checked_srs.md
    AD/ad.puml
    AD/ad.png
```

Language-grouped layout:

```text
Dataset/E-R2A/
  JAVA/
    SmartRecipe/
      checked_srs.md
      AD/ad.puml
      AD/ad.png
  Python/
    prompthub/
      checked_srs.md
      AD/ad.puml
      AD/ad.png
```

Reference diagram candidates:

- `AD/ad.puml`
- `AD/ad.plantuml`
- `AD/ad.wsd`
- `ad.puml`
- `ad.plantuml`
- `ad.wsd`

Requirement document candidates:

- `checked_srs.md`
- `<sample>_review_checklist_srs.md`
- `*_review_checklist_srs.md`
- `*_srs.md`
- `*SRS*.md`
- `*srs*.md`

## Evaluation Layers

### L0: Syntax And Renderability

Implemented in `l0_syntax.py`.

L0 calls PlantUML to render the diagram and then parses nodes and edges with
`plantuml_parser.py`.

Important output fields:

- `l0_valid`
- `l0_errors`
- `l0_warnings`
- `l0_node_count`
- `l0_edge_count`

If L0 fails, the sample is written to CSV with:

```text
stage_status = failed_l0
```

and L1/L2 are skipped for that sample.

Single-file L0 check:

```powershell
python -m evaluation_script.l0_syntax .\path\to\candidate.puml
```

### L1: Structural Evaluation

Implemented in `l1_structural.py`.

Without a reference diagram, L1 can still report intrinsic structural
diagnostics such as predicted node count, edge count, orphan ratio, and god-node
ratio.

With a reference diagram and node alignment, L1 reports:

- node coverage and generated-node precision;
- edge precision, recall, and F1;
- boundary accuracy;
- graph edit distance accuracy and its error decomposition;
- matched and unmatched node counts.

Node alignment may come from:

1. a manually supplied alignment JSON;
2. a cache file named `judge_alignment_<model>.json` in the prediction folder;
3. `--enable-l1-judge`, which calls an OpenAI-compatible model and writes a
   cache file.

Single-file L1 check:

```powershell
python -m evaluation_script.l1_structural `
  --pred .\path\to\predicted.puml `
  --gt .\path\to\AD\ad.puml `
  --requirements .\path\to\checked_srs.md `
  --alignment-cache .\path\to\judge_alignment_<model>.json `
  --out .\evaluation_script\l1_debug.json
```

### L2: Semantic And Evidence Evaluation

Implemented in `l2_semantic.py`.

L2 is an LLM judge that evaluates the generated architecture against the
requirements text. It does not depend on visual similarity to the reference
diagram.

L2 requires:

- `--enable-l2-judge`;
- a requirement document;
- an API key in the environment variable named by `--llm-api-key-env`.

L2 status values include:

- `completed`
- `failed`
- `skipped_disabled`
- `skipped_missing_api_key`
- `skipped_missing_requirements`

L2 score dimensions:

| Field | Meaning |
| --- | --- |
| `l2_completeness_score` | Coverage of requirements, ASRs, and quality drivers. |
| `l2_faithfulness_score` | Avoidance of unsupported components, relations, technologies, and assumptions. |
| `l2_architectural_rationality_score` | Responsibility assignment, dependency choices, boundaries, and quality-attribute handling. |
| `l2_traceability_score` | Whether key elements and decisions can be traced to requirement evidence. |
| `l2_readability_score` | Whether the diagram is clear and reviewable. |

Auxiliary L2 metrics:

- `l2_requirement_coverage`
- `l2_asr_coverage`
- `l2_unsupported_inference_rate`

## CSV Output

`pipeline.py` defines the stable CSV field order.

Metadata fields:

- `sample_id`
- `candidate_id`
- `workflow`
- `model_id`
- `project_language`
- `stage_status`

L0 fields:

- `l0_valid`
- `l0_errors`
- `l0_warnings`
- `l0_node_count`
- `l0_edge_count`

L1 fields:

- `l1_status`
- `l1_error`
- `l1_predicted_node_count`
- `l1_predicted_edge_count`
- `l1_reference_node_count`
- `l1_reference_edge_count`
- `l1_node_coverage`
- `l1_gen_precision`
- `l1_edge_precision`
- `l1_edge_recall`
- `l1_edge_f1`
- `l1_boundary_accuracy`
- `l1_ged_accuracy`
- `l1_absolute_ged`
- `l1_ged_missed_node_count`
- `l1_ged_hallucinated_node_count`
- `l1_ged_boundary_error_count`
- `l1_ged_missing_edge_count`
- `l1_ged_hallucinated_edge_count`
- `l1_orphan_ratio`
- `l1_god_ratio`
- `l1_matched_node_count`
- `l1_unmatched_predicted_node_count`
- `l1_unmatched_reference_node_count`

L2 fields:

- `l2_status`
- `l2_completeness_score`
- `l2_faithfulness_score`
- `l2_architectural_rationality_score`
- `l2_traceability_score`
- `l2_readability_score`
- `l2_requirement_coverage`
- `l2_asr_coverage`
- `l2_unsupported_inference_rate`
- `l2_completeness_reasoning`
- `l2_faithfulness_reasoning`
- `l2_architectural_rationality_reasoning`
- `l2_traceability_reasoning`
- `l2_readability_reasoning`
- `l2_raw_json`
- `l2_error`

Internal path fields such as `pred_path`, `gt_path`, and `requirements_path`
are not included in the final CSV output.

## Human Review Workflow

The review workflow is file-based. `prepare_review.py` selects candidate rows,
collects the metadata needed for inspection, and writes a JSON file that can be
used by an external annotation tool or a custom review form.

Prepare review samples:

```powershell
python -m evaluation_script.prepare_review `
  --results .\Output\results_g_r2a.csv `
  --dataset-dir .\Dataset\G-R2A `
  --pred-root .\Output\G-R2A `
  --asset-dir .\review\assets `
  --render-candidates `
  --strategy stratified `
  --n 30 `
  --seed 13 `
  --out .\review\samples.json
```

Useful options:

| Option | Description |
| --- | --- |
| `--results` | One or more evaluation CSV files to sample from. |
| `--strategy random` | Uniform random sampling. |
| `--strategy stratified` | Balanced sampling across dataset, workflow, and model strata. |
| `--n` | Number of candidate diagrams to draw. |
| `--seed` | Random seed for reproducible sampling. |
| `--dataset-dir` | Dataset root used to locate reference SRS files and reference images. |
| `--pred-root` | Prediction root used to locate candidate `predicted.puml` files. |
| `--asset-dir` | Optional directory for copied/rendered image assets. |
| `--render-candidates` | Render selected candidate PlantUML files into assets when PlantUML is configured. |
| `--allow-missing-candidate-image` | Keep selected rows even when candidate images are missing. |

Compare collected human reviews with model scores:

```powershell
python -m evaluation_script.compare_human `
  --review-json .\review\human_reviews.json `
  --out .\review\human_comparison.csv
```

For reliable comparison, preserve stable identifiers in the review data:

- `sample_id`
- `candidate_id`
- `workflow`
- `model_id`

## Reproducible Workflow

A typical run has four stages:

1. Run L0/L1 evaluation and inspect `failed_l0` cases.
2. Enable or reuse L1 node-alignment caches.
3. Enable L2 semantic judging for requirement-grounded scoring.
4. Generate JSON review samples and compare collected human review with L2
   scores.

Example:

```powershell
python -m evaluation_script.evaluate `
  --pred .\Output\E-R2A `
  --dataset-dir .\Dataset\E-R2A `
  --enable-l1-judge `
  --l1-judge-model <alignment-judge-model> `
  --enable-l2-judge `
  --llm-model <semantic-judge-model> `
  --out .\Output\results_e_r2a.csv
```

To resume a partial run:

```powershell
python -m evaluation_script.evaluate `
  --pred .\Output\E-R2A `
  --dataset-dir .\Dataset\E-R2A `
  --resume-from .\Output\results_e_r2a.csv `
  --out .\Output\results_e_r2a.csv
```

To restrict the run to rows already present in the resume CSV:

```powershell
python -m evaluation_script.evaluate `
  --pred .\Output\E-R2A `
  --dataset-dir .\Dataset\E-R2A `
  --resume-from .\Output\results_e_r2a.csv `
  --only-resume-rows `
  --out .\Output\results_e_r2a.csv
```

## Troubleshooting

### `PlantUML renderer is not configured`

Set `PLANTUML_CMD`, set `PLANTUML_JAR`, or make sure `plantuml` is available on
`PATH`.

### `No PlantUML files found`

Check that `--pred` points to a file or directory containing `.puml`,
`.plantuml`, or `.wsd` files.

### `L1 alignment required but unavailable`

Provide a `judge_alignment_<model>.json` cache, or rerun with
`--enable-l1-judge` and a configured API key.

### `l2_status=skipped_missing_requirements`

The script could not find a requirement document. Check `--dataset-dir`, or pass
`--requirements-dir` explicitly.

### `l2_status=skipped_missing_api_key`

L2 was enabled, but the environment variable named by `--llm-api-key-env` was
empty or missing.

### `ModuleNotFoundError: evaluation_script`

Run commands from the repository root with `python -m ...`, not from inside the
`evaluation_script/` directory.

## Release Hygiene

Before publishing a replication package:

- replace all real API keys with placeholders;
- avoid absolute local paths in README files, CSV files, JSON logs, and scripts;
- remove generated Python caches such as `__pycache__/`;
- remove or sanitize raw agent logs if they contain local paths or credentials;
- keep examples repository-relative;
- document model names, judge endpoints, and run dates separately from secrets.
