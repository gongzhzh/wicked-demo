
# Cycle 1 Experiments (Scripted Dialogue Assessment)

This folder contains the materials and artifacts for **Cycle 1** of our research evaluation.
Cycle 1 includes two scripted dialogue experiments targeting different evaluation goals. 

(1) **Magnitude** is assessed via a treatment-vs-control comparison, measuring whether the treatment induces the intended creativity-support communication patterns more strongly than the baseline. 

(2) **Consistency (robustness)** is assessed by varying dialogue settings (e.g., user personas and prompt formulations) and examining whether the same patterns persist with limited variation. 

Together, the two experiments capture both the strength of the intended behaviors and their stability under controlled changes.

Cycle 1 uses two conditions:
- **Control group:** baseline chatbot configuration
- **Treatment group:** targeted system instructions + web-based retrieval (and our multi-agent setup)

## Folder structure
- `control-group/`
  - Artifacts and logs for the baseline condition (scripted dialogues and coding outputs).
- `treat-group/`
  - Artifacts and logs for the treatment condition (scripted dialogues and coding outputs).
- `Calibration Exercise.docx`
  - Coding calibration material (definitions, examples, and coder alignment exercise).
- `Dialogue Annotation Results.pptx`
  - Summary slides of Cycle 1 annotation(coding) outcomes (figures/tables used in reporting).

## How to use these artifacts
If you only want to **inspect results**:
1. Open `Dialogue Annotation Results.pptx` for the summarized findings.
2. Use `Calibration Exercise.docx` to understand the coding scheme and decision rules.
3. Browse `control-group/` and `treat-group/` to see the underlying dialogue/annotation artifacts.

If you want to **reproduce Cycle 1**:
- See the repository root documentation for environment setup and how to run the assistant.
- Then run the Cycle 1 pipeline and place generated outputs under the corresponding group folder.

> Note: Exact run commands may differ by environment. Keep this folder focused on artifacts and experiment structure.

## Data and privacy notes
- These artifacts are intended for research transparency and reproducibility.
- If any dialogue content includes sensitive information, keep it anonymized or store raw data outside the repo.

## Citation
If you use the artifacts in this folder, please cite the repository and the manuscript metadata (contact us if provided).
