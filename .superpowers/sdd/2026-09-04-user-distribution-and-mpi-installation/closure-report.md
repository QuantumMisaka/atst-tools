# Post-publication closure report

**Date:** 2026-09-06
**Release:** `2.2.4`
**Tag:** `v2.2.4` → `eaac64a76215e33588d362a788c138464519a7ba`

## Closure result

The active release documentation now describes the published `2.2.4` release.
The local README and active user/developer navigation were updated from
release-candidate/pending wording. Historical candidate and `2.2.3` records
remain dated and intact. The HTML spec and documentation status ledger record
publication, GitHub/PyPI verification, and the explicit exclusion of Gitee
rendering verification.

The release notes also record the known cosmetic limitation that the uploaded
PyPI README is immutable and retains the prepublication candidate wording. No
new patch release, retag, or republish was made or is needed.

## Evidence

- GitHub Release: <https://github.com/QuantumMisaka/atst-tools/releases/tag/v2.2.4>
- GitHub Tests run `33980730827`: success.
- GitHub abacuslite run `33980730831`: success.
- GitHub PyPI publication run `33980788260`: success.
- Tag `v2.2.4` resolves to the exact commit above.
- [PyPI JSON](https://pypi.org/pypi/atst-tools/2.2.4/json) lists the wheel and
  source distribution; the [rendered project page](https://pypi.org/project/atst-tools/2.2.4/)
  shows four absolute GitHub/Gitee guide and example links.
- Clean verification in `/tmp/atst-224-pypi-verify.7qwIIs/venv` installed
  `atst-tools==2.2.4` from PyPI, passed `pip check`, reported `2.2.4` from
  `atst --version`, imported the package outside the repository, loaded stable
  API imports, and found no `mpi4py` module.
- The tagged CI repair registers the documented point-KPT parser patch in the
  abacuslite drift checker while retaining unrelated-drift rejection.

## Scoped changes

Only release documentation, README, the original plan/spec/status ledger, and
this report were changed. Runtime code, workflows, version metadata, and
external mirrors were not changed. Gitee rendering verification and mirror
synchronization were explicitly out of scope.

## Documentation checks

The closure edits were checked with:

```text
conda run -n atst-dev python scripts/check_docs_governance.py
git diff --check -- README.md docs examples/README.md AGENTS.md
rg -n "^<<<<<<<|^=======|^>>>>>>>" README.md docs examples/README.md AGENTS.md
```

The governance checker passed; the whitespace check had no output; and the
conflict-marker scan had no matches.
