# Shared betting package

This wheel is built from `BG.Analytics.CFB/cfb_betting`, version 0.1.0.
The dashboard installs it through its root requirements.txt and does not import
from a sibling checkout or an unpublished Git branch.

Rebuild from the analytics repository with:

```sh
python -m build --wheel --no-isolation --outdir /path/to/BG.Analytics.CFB.Dash/vendor
```

Commit the rebuilt wheel with dashboard changes that require it. Keep the engine
source, package version, and model/feature/tier versions documented in the analytics
repository's `docs/betting_handoff.md`.
