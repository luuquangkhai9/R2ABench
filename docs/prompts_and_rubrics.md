# Public Prompts And Rubrics

This document collects public prompts and rubrics that are part of the
R2ABench replication package. Evaluation implementation details live in
`evaluation_script/README.md`.

## PRD/SRS Reconstruction Schema

Requirement documents are normalized into six sections before architecture
generation and evaluation:

1. Introduction: project scope, target users, and pain points.
2. Goals: high-level objectives derived from the source requirements.
3. Functional Features: behavior written in a trigger/action style.
4. Technical Constraints: explicit implementation constraints only.
5. Non-Functional Requirements: quality attributes such as performance,
   reliability, security, portability, and maintainability.
6. System Architecture Description: high-level layer descriptions and
   interactions when source evidence supports them.

The reconstruction process is evidence-driven. Inferred requirements should be
marked or excluded unless they are supported by the original material.

## E-R2A Source Extraction Rules

The E-R2A construction helper follows these deterministic extraction rules
before LLM-assisted SRS normalization:

1. Source documents are discovered as project-local files whose names contain
   `_origin` and whose extension is `.md`, `.txt`, `.docx`, or `.pdf`.
2. Source text is split by headings when possible; oversized sections are split
   into paragraph-based chunks while preserving source line ranges.
3. Each evidence item receives a stable ID, a repository-relative source
   location, an evidence type, coarse categories, extracted facts, and the raw
   excerpt.
4. Evidence categories are assigned with conservative keyword rules covering
   functional behavior, non-functional qualities, technical constraints,
   architecture, data, and actors.
5. Only explicit source-supported facts should be used in downstream SRS
   construction. Unsupported assumptions should be excluded or marked as out of
   scope.
6. The normalized SRS must preserve traceability by citing evidence item IDs for
   every functional requirement, non-functional requirement, constraint, data
   requirement, external interface, assumption, and ASR.

## E-R2A SRS Normalization Prompt

```text
Role: You are a requirements engineer preparing a standardized SRS for a
requirements-to-architecture benchmark.

Task: Convert the provided source evidence pack into a concise, evidence-bound
software requirements specification.

Requirements:
1. Use only facts supported by the evidence pack. Do not invent requirements,
   technologies, APIs, components, deployment decisions, or quality attributes.
2. Preserve evidence traceability. Every FR, NFR, technical constraint, data
   requirement, external interface, assumption/dependency, and ASR must cite one
   or more evidence IDs.
3. Normalize the SRS into these sections:
   - Introduction and product scope
   - Overall description, user classes, and operating environment
   - External interface requirements
   - Functional requirements
   - Data requirements
   - Non-functional requirements
   - Technical constraints
   - Assumptions and dependencies
   - Architecturally significant requirements
   - Traceability matrix
4. Write functional requirements in a trigger/input, system behavior, output,
   priority, verification, and source-evidence format.
5. Keep technical constraints separate from requirements. Mention frameworks,
   databases, protocols, and deployment details only when they are supported by
   evidence.
6. If source material is ambiguous, write a conservative requirement or mark the
   item as out of scope instead of over-inferring.
7. Output Markdown only.

Input:
{evidence_pack_json}
```

## Reference Architecture Conversion Prompt

```text
Role: You are a software architecture annotator converting a reference
architecture view into PlantUML.

Task: Reconstruct the provided architecture view as a parseable PlantUML
component or deployment diagram while preserving the original structure.

Requirements:
1. Preserve the original component hierarchy, layer/package boundaries,
   external systems, data stores, and directed relations as faithfully as
   possible.
2. Do not add components, technologies, or relations that are not visible in
   the reference view or supported by the accompanying SRS/evidence.
3. Use standard PlantUML component/deployment syntax that can be rendered by
   PlantUML.
4. Prefer readable component names and stable package boundaries over visual
   styling.
5. If a label is ambiguous, keep the original wording and avoid guessing.
6. Output only PlantUML code beginning with @startuml and ending with @enduml.

Inputs:
- Reference architecture image or source view: {architecture_view}
- Optional checked SRS/evidence context: {checked_srs_or_evidence}
```

## Architecture Generation Prompt

```text
Role: You are an experienced software architect.

Task: Read the provided requirements document and generate a system
architecture diagram.

Requirements:
1. Generate a layered component or deployment diagram.
2. Do not generate sequence diagrams, use-case diagrams, or class diagrams.
3. Use standard PlantUML component/deployment syntax.
4. Include architectural components, storage systems, gateways, external
   services, and structural dependencies that are supported by the requirements.
5. Output only PlantUML code beginning with @startuml and ending with @enduml.

Input:
{prd_text}
```

## Node Alignment Prompt Schema

The L1 judge compares reference and predicted node lists with requirement
context. Nodes are represented with hierarchical labels such as
`Backend::Auth Service` or `Global::Payment Provider`.

The expected JSON schema is:

```json
{
  "matched_pairs": [
    {
      "gt_nodes": ["Backend::Auth Service"],
      "predicted_nodes": ["Gateway::Auth Center"],
      "match_type": "1:1",
      "is_boundary_correct": false,
      "reasoning": "The nodes are functionally related, but the predicted boundary is different."
    }
  ],
  "unmatched_gt_nodes": ["Global::Payment API"],
  "unmatched_predicted_nodes": ["Client::Router"]
}
```

Allowed match types include exact semantic matches, generalization or
specialization matches, split matches, and merge matches. Boundary correctness
is judged by architectural semantics rather than literal string equality.

## L2 Semantic Judge Rubric

L2 uses five primary dimensions:

| Dimension | Question |
| --- | --- |
| Completeness | Does the diagram cover the main requirements, ASRs, and quality drivers? |
| Faithfulness | Does it avoid unsupported components, relations, technologies, and assumptions? |
| Architectural Rationality | Are responsibilities, dependencies, boundaries, and quality-attribute tactics reasonable? |
| Traceability | Can key elements and decisions be traced back to requirements or evidence? |
| Readability | Is the diagram clear, reviewable, and appropriately organized? |

Each dimension is scored on a 1-5 scale. L2 also records requirement coverage,
ASR coverage, unsupported inference rate, and short textual reasoning for each
dimension.
