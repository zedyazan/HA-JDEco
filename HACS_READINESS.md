# HACS readiness audit

Audit branch: `audit/hacs-readiness`  
Repository: [zedyazan/HA-JDEco](https://github.com/zedyazan/HA-JDEco)

## Result

**Not ready for HACS publication yet.** The code has a substantial Home Assistant integration implementation, but the repository layout currently prevents a normal HACS installation and the automated validation workflow was stored at the repository root instead of under `.github/workflows/`.

## Blocking findings

1. **Integration package is in the repository root.** HACS metadata sets `content_in_root` to `false` and `filename` to `jdeco`, which requires the integration at `custom_components/jdeco/`. The current files (`__init__.py`, `manifest.json`, platform modules, translations, and helpers) are at the root.
2. **Translations are in the wrong location.** Home Assistant expects `strings.json` in the integration directory and user translations under `custom_components/jdeco/translations/` (for example `translations/en.json` and `translations/ar.json`).
3. **The existing workflow is misplaced.** `validate.yml` at the repository root is not a GitHub Actions workflow. A real workflow has been added at `.github/workflows/validate.yml`; the root duplicate should be removed during the package move.
4. **The proxy helper has an undeclared dependency.** `proxy_connector.py` imports `python_socks`, while `manifest.json` declares no requirement. Although Tor is disabled, `__init__.py` imports the proxy module at integration import time. Either remove the unused Tor implementation or declare and verify a compatible dependency before release.

## High-priority code findings

- `async_setup_entry` converts connection failures into `ConfigEntryAuthFailed`; transient network failures should normally raise `ConfigEntryNotReady`, while authentication failures should use `ConfigEntryAuthFailed`.
- The client logs the first 200 characters of a failed response in `client.py`. Keep protocol diagnostics at debug level and ensure plaintext/error responses cannot expose account data.
- Diagnostics and entity states expose account identifiers, meter identifiers, receipt values, and STS tokens. Review whether these should be redacted or disabled by default before requesting public issue reports.
- There are no repository tests. Add unit tests for cryptography round trips, WCF date parsing, response parsing, retry/session-expiry handling, diagnostics redaction, and config-flow error mapping.
- `_current_month_totals` selects the newest month present in the server response rather than explicitly filtering to the current month. Confirm the intended behavior and add a regression test.
- The README and audit report make production/testing claims that are not reproducible from the repository. Replace claims such as live-environment verification with documented CI or externally verifiable release evidence.

## Required packaging move

Move the integration implementation into this layout before merging:

```text
custom_components/
  jdeco/
    __init__.py
    manifest.json
    config_flow.py
    const.py
    client.py
    crypto.py
    coordinator.py
    diagnostics.py
    models.py
    sensor.py
    binary_sensor.py
    button.py
    strings.json
    translations/
      en.json
      ar.json
```

Keep repository-level files such as `README.md`, `LICENSE`, `CHANGELOG.md`, `hacs.json`, and `.github/workflows/validate.yml` at the root. Remove the old root-level integration files after the move so HACS cannot discover an ambiguous package.

## Release gate

Do not publish to the HACS default repository until:

- the package move is complete;
- HACS Action and hassfest pass on the default branch;
- the undeclared `python_socks` dependency is removed or formally supported;
- unit tests cover the security and retry paths;
- manifest links point to this repository;
- a tagged semantic-version release is created; and
- a clean Home Assistant installation is tested using the HACS-installed package.
