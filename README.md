# AequilibraE

[![Downloads](https://img.shields.io/pypi/dm/aequilibrae.svg?maxAge=2592000)](https://pypi.python.org/pypi/aequilibrae)
[![Documentation](https://github.com/AequilibraE/aequilibrae/actions/workflows/documentation.yml/badge.svg)](https://github.com/AequilibraE/aequilibrae/actions/workflows/documentation.yml)
[![unit tests](https://github.com/AequilibraE/aequilibrae/actions/workflows/unit_tests.yml/badge.svg)](https://github.com/AequilibraE/aequilibrae/actions/workflows/unit_tests.yml)
[![Code coverage](https://github.com/AequilibraE/aequilibrae/actions/workflows/test_linux_with_coverage.yml/badge.svg)](https://github.com/AequilibraE/aequilibrae/actions/workflows/test_linux_with_coverage.yml)
[![Packaging](https://github.com/AequilibraE/aequilibrae/actions/workflows/build_wheels.yml/badge.svg)](https://github.com/AequilibraE/aequilibrae/actions/workflows/build_wheels.yml)

AequilibraE is an open-source transportation modeling package for Python 3.10+,
released under a permissive, business-friendly license.

It is designed as general-purpose modeling software and imposes very little
structure on models built with it. Many core algorithms can also be used without
an AequilibraE project by working directly with pandas DataFrames and NumPy
arrays, which makes the package useful when transportation modeling is one
component of a larger analytical pipeline.

## What it provides

- Project-based network modeling backed by SQLite/SpatiaLite databases.
- Network editing through the Python API, SQL, or GIS tools that support SpatiaLite.
- Data integrity support through spatial database triggers.
- Native AequilibraE matrices, OMX matrix interoperability, sparse matrices, and skim outputs.
- Multi-class traffic assignment with class-specific networks, value of time, generalized costs, MSA, Frank-Wolfe, conjugate Frank-Wolfe, and biconjugate Frank-Wolfe workflows.
- Public transport support including GTFS import, route map matching, transit graph construction, preloading, and Optimal Strategies transit assignment.
- Trip distribution models, including gravity models and cache-optimized IPF.
- OSM and GMNS network import/export support.
- VISUM network import from SQLite and GeoJSON, including zone polygons, centroids, connectors, and deterministic source-ID topology validation.
- VISUM SQLite public-transport import and GTFS import with network-coverage analysis and route-geometry synthesis where shapes are missing.
- OMX and native matrix import through the project matrix gateway.
- Federated model assembly when network, demand, and transit come from different sources: geometry-based reconciliation and heuristics (for example spread-based centroid connector placement when connectors are absent).
- Performance-critical Cython kernels built with C++17 and OpenMP.

Import paths for network, demand, and transit were developed and validated primarily against **VISUM-oriented examples** (including Karlsruhe). They should also be exercised on inputs from **other origins** to determine how universal the current interfaces and heuristics are versus VISUM-specific assumptions. See `docs/backlog.md` for the planned fine-tuning and validation stages.

AequilibraE project data is primarily stored in SQLite/SpatiaLite databases,
with matrix files stored alongside the project. This keeps project data in
widely supported formats while allowing AequilibraE to maintain consistency
between links, nodes, zones, modes, matrices, results, scenarios, and transit
data.

## Development status

AequilibraE is developed in the open and uses GitHub Actions for linting,
testing, coverage, documentation, source distributions, and wheels. The test
workflow covers Windows, Ubuntu Linux, and macOS across Python 3.10 through
3.14. The current wheel workflow builds on Ubuntu, Windows, and Ubuntu ARM.

For local development:

```bash
pip install -e ".[dev]"
pytest tests/ --durations=50 --dist=loadscope -n 4 --random-order --verbose
ruff check aequilibrae/
```

The Sphinx documentation lives under `docs/`, and doctests are part of the
documentation workflow.

This repository also contains OpenSpec/Codex/Copilot/Cursor context for
spec-driven brownfield development. See `AGENTS.md` for agent operating rules,
`openspec/project.md` for the detailed project architecture snapshot, and
`docs/backlog.md` for the development roadmap.

## Comprehensive documentation

[AequilibraE documentation built with Sphinx ](http://www.aequilibrae.com)


### What is available only in QGIS

Some common resources for transportation modeling are inherently visual, and therefore they make more sense if
available within a GIS platform. For that reason, many resources are available only from AequilibraE's 
[QGIS plugin](http://plugins.qgis.org/plugins/qaequilibrae/),
which uses AequilibraE as its computational workhorse and also provides GUIs for most of AequilibraE's tools. Said tool
is developed independently and may lag behind the Python package. More details can be found in its
[GitHub repository](https://github.com/AequilibraE/qaequilibrae).
