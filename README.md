# Fuck-BPF aka Android 16 QPR2 BPF Reverts to support <= 4.19 kernels

![GitHub Stars](https://img.shields.io/github/stars/techyminati/fuck-bpf?style=social)
![Patches](https://img.shields.io/badge/Patches-35-brightgreen?logo=git)
![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)
![Kernel Support](https://img.shields.io/badge/Kernel-4.4%20|%204.9%20|%204.14%20|%204.19-green.svg)

## Overview

This repository contains patches to revert "Bpf Requirements" in AOSP to enable legacy kernels devices (<=  4.19) boot Android 16 QPR2.

## Background

With the release of Android 16 QPR2, Google introduced strict BPF requirements that prevent booting on kernels older than version 5.4. This change rendered numerous devices unable to run Android 16 QPR2, particularly affecting:

- Devices with kernel 4.19 and older kver.

Also, Many devices in the market lack publicly available kernel sources, making it impossible to backport BPF support or upgrade to newer/latest upstream, other than this, sometimes it's infeasible to upstream kernel source due to certain factors (like some oplus devices). The mandatory BPF requirements in Android 16 QPR2 created a hard compatibility barrier, causing boot failures & splash loop on these devices.

## Solution

This repository provides source-level reverts/patches that reverse the BPF requirements, allowing Android 16 QPR2 to boot on devices without full BPF support. The patches implement fallback mechanisms and remove hard dependencies on BPF functionality.

## Current Status

**Tested Configurations:**
- **Kernel 4.19** - Android 16 QPR2 boots successfully
- **Kernel 4.14** - Android 16 QPR2 boots successfully

**Pending Testing:**
- **Kernel 4.9** - Support added, but untested.
- **Kernel 4.4** - Support added, but untested.

**Supported Kernels:**
Support has been added for all kernel versions: **4.4, 4.9, 4.14, and 4.19**. As of now, AOSP by default supports kver >=5.4 .

**Important Notes:**
- If you have tested on 4.9 or 4.4 kernels, please let us know your results!
- Unfortunately, it's not possible to support kernels older than 4.4 at this time.
- If you manage to make older kernels work, please submit a PR!

## Usage

### Use Auto Patch Script
1. Clone this repo in root of your source tree
2. Run command:
```
./fuck-bpf/apply.sh --mb
```

`apply.sh --mb` now applies patches one by one and skips patches whose changes are already present in the target tree.

To preview what will happen without modifying the source tree, run:
```
./fuck-bpf/apply.sh --dry-run
```

Dry-run reports whether each patch would apply cleanly, would be skipped as a duplicate, or would fail.

To verify that all target repos are clean after applying patches, run:
```
./fuck-bpf/apply.sh --verify
```

Verify checks each target repo for a clean working tree and confirms that no `git am` session is still in progress.

If you intentionally want destructive cleanup across target repos, run:
```
./fuck-bpf/apply.sh --cleanup
```

Cleanup aborts any active `git am`, resets patched repos back to the recorded pre-apply base when available, and removes untracked and ignored files such as generated build outputs.

Any missing or unknown mode now prints usage and exits non-zero instead of cleaning repos implicitly.

To validate the patch series against a synced source tree, run:
```bash
FUCK_BPF_SOURCE_ROOT=/path/to/android/source ./scripts/validate-patches.sh
```

This replays every patch series in temporary worktrees under the synced source tree and fails if any series no longer applies cleanly.

The same validation is available in pre-commit when `FUCK_BPF_SOURCE_ROOT` is set.

### Manual Application
Patches can be applied manually to specific components:

```bash
cd /path/to/android/source/component
git am /path/to/this/repo/component/*.patch
```

### Prerequisites

- You have Android 16 QPR2 tree with proper blob patches
- Basic knowledge of Git & Android build system
- Common sense :D


## Contributing

Contributions are welcome. When submitting patches:

1. Follow the existing patch naming convention (0001-description.patch)
2. Ensure patches apply cleanly with `git am`
3. Test on target hardware before submitting
4. Include clear commit messages explaining the change

## Credits

* Patches in this repository are derived from work by multiple contributors, all credits goes to the original author of patches.
* This repository is curated & maintained by [Aryan Sinha](https://github.com/techyminati)

## License
This repo is licensed under Apache License 2.0

## Disclaimer

These patches modify core Android system components. Use at your own risk. Thoroughly test on target hardware before deploying to release. 
