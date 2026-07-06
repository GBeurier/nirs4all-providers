# Security policy

## Scope

`nirs4all-providers` is a soft-importing client layer over optional sibling
packages `nirs4all-datasets` and `nirs4all-repository`.

Security-relevant properties:

- **No network access in this package itself.** The provider layer exposes typed
  adapters and health checks; it does not perform its own HTTP client work.
- **No runtime execution surface.** The release gate explicitly blocks
  execution-like provider capabilities from shipping as supported API.
- **No credential storage.** This repository should not contain tokens, API
  keys, or private datasets.
- **Optional extras stay isolated.** Missing sibling packages degrade to typed
  unavailability instead of import-time crashes.

Issues in backing packages, benchmarks, or papers should also be reported to the
affected repository if the defect lives outside this adapter layer.

## Reporting a vulnerability

Please report security issues **privately**. Do not open a public GitHub issue
for a suspected vulnerability. Email **nirs4all-admin@cirad.fr** with:

- affected version,
- a short description of impact,
- reproduction steps or a minimal proof of concept,
- any mitigation already identified.

We will acknowledge the report as soon as practical and coordinate remediation
and disclosure.
