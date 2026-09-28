# R2ABench

R2ABench is a benchmark for evaluating requirements-to-architecture (R2A)
capabilities. A model or agent reads software requirements, generates a
PlantUML architecture diagram, and is evaluated against reference architecture
views and requirement evidence.

This repository is organized as a paper replication package: it contains the
datasets, generated outputs, aggregate result tables, evaluation scripts, data
construction helpers, and public documentation needed to inspect or reproduce
the reported experiments.

## Task

R2ABench evaluates whether a system can:

1. read a PRD, SRS, or repository-derived requirements document;
2. generate a layered component or deployment architecture view;
3. express the view as valid PlantUML;
4. preserve requirements, architectural boundaries, dependencies, data stores,
   external services, and quality-attribute decisions;
5. support structural and semantic comparison with a curated reference view.

The benchmark focuses on architecture-level reasoning rather than source-code
generation.

## Repository Map

```text
R2ABench/
  Dataset/
    E-R2A/
      JAVA/
      Python/
    G-R2A/
      _agreement/
      selected_candidates.csv
      view_metadata.csv
      SRS.md
      <sample_id>/
  Output/
    E-R2A/
    G-R2A/
    results_e_r2a.csv
    results_g_r2a.csv
    srs_edge_result.csv
  evaluation_script/
    README.md
    evaluate.py
    pipeline.py
    l0_syntax.py
    l1_structural.py
    l2_semantic.py
    plantuml_parser.py
    prepare_review.py
    compare_human.py
  data_construction/
    extract_e_r2a.py
  docs/
    g_r2a_evidence_retrieval.md
    g_r2a_selection_rubric.md
    prompts_and_rubrics.md
    srs_revision_rules.md
```

All documentation examples use repository-relative paths. Local machine paths,
API keys, and private service credentials are not required.

## Artifact Index

| Artifact | Location | Purpose |
| --- | --- | --- |
| E-R2A dataset | `Dataset/E-R2A/` | 17 curated educational/project samples with original requirement material, checked SRS files, evidence packs, and reference architecture views. |
| G-R2A dataset | `Dataset/G-R2A/` | 51 GitHub-derived samples with evidence packs, checked SRS files, reference architecture views, agreement material, and view metadata. |
| Generated outputs | `Output/E-R2A/`, `Output/G-R2A/` | Candidate PlantUML diagrams and per-candidate auxiliary files organized by workflow and model. |
| Aggregate results | `Output/results_e_r2a.csv`, `Output/results_g_r2a.csv` | Released L0/L1/L2 result tables for paper analysis. |
| Edge reachability annotations | `Output/srs_edge_result.csv` | Sampled G-R2A reference-edge annotations used to analyze whether relations are derivable from SRS text. |
| Evaluation scripts | `evaluation_script/` | Batch evaluation, PlantUML parsing, structural metrics, semantic judging, and human-review utilities. |
| Data construction helper | `data_construction/extract_e_r2a.py` | Deterministic E-R2A evidence extraction and prompt-context preparation. |
| Selection rubric | `docs/g_r2a_selection_rubric.md` | G-R2A candidate scoring dimensions, thresholds, metadata fields, and manual filtering rule. |
| Evidence retrieval settings | `docs/g_r2a_evidence_retrieval.md` | BM25/VSM/code-aware retrieval settings, RRF weights, `k=60`, and released evidence-pack trace fields. |
| Public prompts and rubrics | `docs/prompts_and_rubrics.md` | Architecture generation prompt, SRS normalization prompt, reference-view conversion prompt, node-alignment schema, and L2 rubric. |
| SRS revision rules | `docs/srs_revision_rules.md` | English protocol for reviewing model-detected SRS issues and proposed SRS revisions. |

For evaluation commands, CSV column definitions, judge settings, human-review
workflow, and troubleshooting, see `evaluation_script/README.md`.

## Dataset Summary

| Dataset | Samples | Organization | Main use |
| --- | ---: | --- | --- |
| `E-R2A` | 17 | 8 Java projects and 9 Python projects | Controlled project-level R2A evaluation with curated requirement sources and reference architecture diagrams. |
| `G-R2A` | 51 | Direct sample folders named by sample ID | Repository-derived R2A evaluation with selected GitHub architecture views and evidence-grounded SRS files. |

### E-R2A

Each E-R2A project folder contains original requirement material, normalized
SRS files, evidence, and a reference architecture view.

| Pattern | Meaning |
| --- | --- |
| `<project>_origin.md`, `<project>_origin.docx`, or `<project>_origin.pdf` | Original source requirement document. |
| `<project>_C.md`, `<project>_E.md` | Chinese and English PRD/SRS-style reconstructions. |
| `<project>_srs.md`, `checked_srs.md` | Structured SRS and checked canonical SRS used for evaluation. |
| `<project>_evidence_pack.json` | Extracted evidence for auditing and traceability. |
| `AD/ad.puml`, `AD/ad.png` | Reference architecture view in PlantUML and rendered image form. |
| `AD/architecture_diagram.png` | Original or normalized architecture image used during curation. |

The helper `data_construction/extract_e_r2a.py` prepares deterministic source
evidence packs and SRS prompt contexts. Use
`python -m data_construction.extract_e_r2a --help` for its options.

### G-R2A

G-R2A contains 51 final samples. `selected_candidates.csv` records the 52
automatically retained candidates; one candidate was removed after manual
inspection because its architecture diagram did not fully reflect repository
functionality.

Top-level G-R2A files:

| File | Meaning |
| --- | --- |
| `selected_candidates.csv` | Candidate selection metadata and scores. |
| `view_metadata.csv` | One row per final sample with `behavior_type`, `granularity_level`, architectural concern, notation labels, graph statistics, and edge-support summaries. |
| `SRS.md` | Dataset-level SRS/description material. |
| `_agreement/` | Agreement reports and issue-level annotation summaries for G-R2A construction and review. |

Each sample folder follows this shape:

```text
Dataset/G-R2A/<sample_id>/
  checked_srs.md
  final_srs.md
  final_srs_C.md
  evidence_pack.json
  model_srs_review.json
  model_srs_review_raw.md
  human_srs_review*.md
  srs_generation_report.json
  AD/
    ad.puml
    ad.png
    architecture_diagram.png
```

G-R2A construction details are documented in:

| Topic | Documentation |
| --- | --- |
| Candidate scoring and 52-to-51 filtering | `docs/g_r2a_selection_rubric.md` |
| Evidence retrieval settings | `docs/g_r2a_evidence_retrieval.md` |
| SRS issue/revision annotation protocol | `docs/srs_revision_rules.md` |
| Public prompts and judging rubrics | `docs/prompts_and_rubrics.md` |

## Output Summary

`Output/` contains generated architecture diagrams, cached judge files,
execution traces where available, and aggregate result CSV files.

| File or folder | Rows / scope | Meaning |
| --- | ---: | --- |
| `Output/results_g_r2a.csv` | 816 rows | G-R2A results for 51 samples across 4 workflows and 4 models. |
| `Output/results_e_r2a.csv` | 272 rows | E-R2A results for 17 projects across 4 workflows and 4 models. |
| `Output/G-R2A/evidence_l0_l1_l2_results.csv` | 51 rows | Additional G-R2A evidence-chain evaluation output. |
| `Output/srs_edge_result.csv` | 233 rows | Sampled G-R2A reference-edge reachability annotations with repository-relative SRS and PlantUML paths. |
| `Output/<dataset>/<workflow>/<model>/<sample_id>/` | per candidate | Generated `predicted.puml` files and auxiliary run artifacts. |

Released workflows:

| Workflow | Description |
| --- | --- |
| `direct` | Direct prompting baseline. |
| `metagpt-custom` | Custom MetaGPT-style multi-agent workflow. |
| `mini-swe-agent` | Mini-SWE-agent workflow with task and trajectory records. |
| `openhands` | OpenHands-based workflow with execution logs where available. |

Released model folders include `claude-sonnet-4-6`, `deepseek-v3.2`, `gpt-5`,
and `qwen3-coder-480b-a35b-instruct`.

## Evaluation

Evaluation code and operational documentation live in `evaluation_script/`.
That README covers:

- environment setup and PlantUML configuration;
- batch evaluation commands;
- L0 syntax/renderability checks;
- L1 structural matching and node-alignment caches;
- L2 semantic judging;
- CSV output fields;
- human review sample preparation and comparison;
- troubleshooting.

Start there for running or re-running experiments:

```text
evaluation_script/README.md
```

## View Metadata For Grouped Analysis

`Dataset/G-R2A/view_metadata.csv` supports grouped analysis by architecture
view characteristics. Join it with `Output/results_g_r2a.csv` on `sample_id`.

| Factor | Categories | Sample counts |
| --- | --- | --- |
| `behavior_type` | `static`, `dynamic`, `mixed` | 28, 17, 6 |
| `granularity_level` | `high`, `medium`, `low` | 23, 23, 5 |

The file also includes architectural concern labels, notation/style labels,
reference graph size, and edge-support summaries. The underlying sampled edge
annotations are in `Output/srs_edge_result.csv`; 48 samples have sampled edge
annotations, and 3 samples are marked as `not_sampled_in_srs_edge_result`.

## Reproducibility Notes

- Use aggregate CSV files for paper tables unless you need to audit individual
  candidate artifacts.
- Use `evaluation_script/README.md` for runnable evaluation commands and judge
  configuration.
- Use `docs/` for construction protocols, prompts, rubrics, candidate scoring,
  and evidence-retrieval settings.
- Raw agent logs and trajectories are included where available for auditability;
  sanitize them before redistribution if your release policy excludes local
  execution traces.

## Dataset Statistics

| Dataset | Samples | Workflows | Models | Result rows |
| --- | ---: | ---: | ---: | ---: |
| G-R2A | 51 | 4 | 4 | 816 |
| E-R2A | 17 | 4 | 4 | 272 |

| Folder | Files | Approx. size |
| --- | ---: | ---: |
| `Dataset/E-R2A/` | 153 | 32 MB |
| `Dataset/G-R2A/` | 779 | 20 MB |
| `Output/E-R2A/` | 595 | 5 MB |
| `Output/G-R2A/` | 2,392 | 13 MB |
| `evaluation_script/` | 10 source/doc files | less than 1 MB |
| `data_construction/` | 2 source files | less than 1 MB |
| `docs/` | 4 | less than 1 MB |

## Citation

If you use this dataset or evaluation framework, please cite the associated
paper once citation metadata is available. A future release can add
`CITATION.cff` and BibTeX metadata.
