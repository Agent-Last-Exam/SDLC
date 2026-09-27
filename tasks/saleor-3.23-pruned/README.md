# Saleor 3.23 Golden Pruning Harbor Package Builder

This directory owns the Harbor task definition and package export. It
references published runtime image digests but does not build application
runtime images.

- `package.yaml`, `manifest.json`, and `instruction.md` define the task.
- `env/` contains the existing E inputs and their baseline manifest.
- `patches/` contains the final pruned G and bound T inputs.
- `verifier/` constructs C as `E + T` and D as `E + T + G`, then grades the
  frozen F2P/P2P selection.
- `calibration/source-selection.json` preserves the exact recalibration
  evidence; `calibration/selection.json` is its package-schema projection.
- `calibration/audit-summary.json` records the source reports, patch identity,
  suite counts, reruns, and target-side exclusions.

The official exporter writes the generated `standard/` delivery. Generated
files must not be edited as builder source.
