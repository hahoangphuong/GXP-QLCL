# Phase 6 Desktop Evidence Baseline

## Goal
Capture trustworthy evidence for the inspector desktop workflow:
- private-share reachability
- Explorer navigation
- Word desktop open/edit/save
- disconnect/reconnect handling
- multi-user lock behavior

## Delivered
- environment probe: [tools/build_phase6_environment_probe.py](/D:/GXP-QLCL/tools/build_phase6_environment_probe.py)
- local Word harness: [tools/run_phase6_word_desktop_harness.py](/D:/GXP-QLCL/tools/run_phase6_word_desktop_harness.py)
- evidence validator: [tools/validate_phase6_desktop_evidence.py](/D:/GXP-QLCL/tools/validate_phase6_desktop_evidence.py)
- scenario matrix: [desktop_validation_matrix.template.json](/D:/GXP-QLCL/artifacts/phase6/desktop_validation_matrix.template.json)

## What the tooling proves
### Environment probe
- Word desktop exists on the machine
- Word COM automation is callable
- Explorer is present
- SMB mappings can be observed
- Tailscale presence can be observed

### Local Word harness
- a real `.docx` can be created, reopened, edited, saved, and verified through Microsoft Word desktop
- this proves the desktop Office path itself is viable on the current machine

### Validator
- required Phase 6 scenarios must be marked `pass` before the phase can be considered closed
- disconnected SMB mappings and unexecuted private-share scenarios keep the phase `blocked`

## What the tooling does not prove
- active Synology/private-share reachability
- save behavior on a live SMB path
- Explorer navigation on the active share
- disconnect/reconnect recovery on private networking
- two-user contention on the same live share file

## Current evidence from this machine
- Word desktop executable is present
- Word COM is available
- Explorer is available
- a disconnected SMB mapping to Synology is visible
- no active SMB mapping is currently available
- no `tailscale` executable was detected in PATH

## Consequence
Phase 6 tooling baseline is complete, but the operational gate remains blocked until the required private-share scenarios are executed against an active path.
