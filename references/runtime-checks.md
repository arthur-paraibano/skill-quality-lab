# Runtime syntax checks

The core audit parses Python, JSON, TOML, and YAML with bundled Python libraries. When available on `PATH`, it checks Shell with `bash -n`, JavaScript with `node --check`, TypeScript with `tsc --noEmit`, and PowerShell with its parser API.

Report each applicable result as `passed`, `failed`, or `not_assessed`. A missing optional checker is not a successful check and does not fail a portable audit by itself. Declare it in coverage and require the relevant runtime in a release environment that claims support for that language.

The structural score is a finding-severity heuristic: subtract 20 per error and 7 per warning, with a floor of zero. Report the separate applicable-check pass percentage so `100/100` is never presented as universal correctness or safety.
