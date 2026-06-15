"""Opt-in Karlsruhe connector inference experiment (k-NN baseline).

Run repeatedly while tuning inference rules:

    pytest tests/aeq/project/test_karlsruhe_connector_inference.py -v -s \\
        --visum-geojson-folder="C:/path/to/Karlsruhe"
"""

from __future__ import annotations

import pytest

from tests.aeq.project.karlsruhe_connector_validation import (
    DEFAULT_INFERENCE_MODES,
    bootstrap_visum_network_without_connectors,
    external_visum_geojson_folder,
    infer_connectors_knn,
    infer_connectors_spread,
    internal_and_external_zone_ids,
    load_ground_truth_connector_pairs,
    load_inferred_connector_pairs,
    load_zone_demand_from_omx,
    score_all_mode_accuracies,
    score_matrix_mode_accuracy,
)

# Reference accuracy on Karlsruhe (2026-06-12), matrix modes car (c) + hgv (h):
#   k=1: coverage ~0.17, noise ~0.67 (516+515 spurious of 1541 inferred triples)
#   k=2: coverage ~0.28, noise ~0.73 (2327 spurious of 3186 inferred triples)
ACCURACY_FLOORS = {
    1: {"coverage": 0.14, "max_noise": 0.72},
    2: {"coverage": 0.24, "max_noise": 0.76},
}


@pytest.fixture
def visum_karlsruhe_folder(request):
    return external_visum_geojson_folder(request)


@pytest.fixture
def karlsruhe_ground_truth(visum_karlsruhe_folder):
    return load_ground_truth_connector_pairs(visum_karlsruhe_folder)


@pytest.fixture
def karlsruhe_project_without_connectors(empty_project, visum_karlsruhe_folder):
    deleted = bootstrap_visum_network_without_connectors(empty_project, visum_karlsruhe_folder)
    assert deleted > 0, "Expected VISUM import to include centroid connectors before stripping"
    return empty_project


def test_strip_and_reinfer_creates_connectors(karlsruhe_project_without_connectors, visum_karlsruhe_folder):
    project = karlsruhe_project_without_connectors
    zone_ids = project.zoning.data.zone_id.tolist()
    internal_ids, external_ids = internal_and_external_zone_ids(visum_karlsruhe_folder, zone_ids)

    assert len(internal_ids) == 468
    assert len(external_ids) == 258

    infer_connectors_knn(
        project,
        internal_zone_ids=internal_ids,
        external_zone_ids=external_ids,
        modes=DEFAULT_INFERENCE_MODES,
        k_connectors=1,
    )

    inferred = load_inferred_connector_pairs(project)
    assert len(inferred) > 0
    assert inferred["zone_no"].nunique() == len(zone_ids)


@pytest.mark.parametrize("k_connectors", [1, 2])
def test_knn_accuracy_against_ground_truth(
    karlsruhe_project_without_connectors,
    visum_karlsruhe_folder,
    karlsruhe_ground_truth,
    k_connectors,
):
    project = karlsruhe_project_without_connectors
    zone_ids = project.zoning.data.zone_id.tolist()
    internal_ids, external_ids = internal_and_external_zone_ids(visum_karlsruhe_folder, zone_ids)

    infer_connectors_knn(
        project,
        internal_zone_ids=internal_ids,
        external_zone_ids=external_ids,
        modes=DEFAULT_INFERENCE_MODES,
        k_connectors=k_connectors,
    )
    inferred = load_inferred_connector_pairs(project)
    combined = score_matrix_mode_accuracy(karlsruhe_ground_truth, inferred)
    per_mode = score_all_mode_accuracies(karlsruhe_ground_truth, inferred)

    floors = ACCURACY_FLOORS[k_connectors]
    print(f"k={k_connectors}")
    print(
        "combined "
        f"coverage={combined.coverage:.3f} ({combined.covered_connectors}/{combined.ground_truth_connectors}) "
        f"noise={combined.noise_rate:.3f} ({combined.spurious_connectors}/{combined.inferred_connectors})"
    )
    for accuracy in per_mode:
        print(
            f"mode={accuracy.mode} "
            f"coverage={accuracy.coverage:.3f} "
            f"({accuracy.covered_connectors}/{accuracy.ground_truth_connectors}) "
            f"noise={accuracy.noise_rate:.3f} "
            f"({accuracy.spurious_connectors}/{accuracy.inferred_connectors})"
        )

    for accuracy in per_mode:
        assert accuracy.coverage >= floors["coverage"]
        assert accuracy.noise_rate <= floors["max_noise"]

    assert combined.coverage >= floors["coverage"]
    assert combined.noise_rate <= floors["max_noise"]


def test_spread_heuristic_against_ground_truth(
    karlsruhe_project_without_connectors,
    visum_karlsruhe_folder,
    karlsruhe_ground_truth,
):
    project = karlsruhe_project_without_connectors
    zone_ids = project.zoning.data.zone_id.tolist()
    internal_ids, external_ids = internal_and_external_zone_ids(visum_karlsruhe_folder, zone_ids)
    zone_demand = load_zone_demand_from_omx(visum_karlsruhe_folder)

    infer_connectors_spread(
        project,
        internal_zone_ids=internal_ids,
        external_zone_ids=external_ids,
        modes=DEFAULT_INFERENCE_MODES,
        zone_demand=zone_demand,
    )
    inferred = load_inferred_connector_pairs(project)
    combined = score_matrix_mode_accuracy(karlsruhe_ground_truth, inferred)
    per_mode = score_all_mode_accuracies(karlsruhe_ground_truth, inferred)

    print("spread heuristic")
    print(
        "combined "
        f"coverage={combined.coverage:.3f} ({combined.covered_connectors}/{combined.ground_truth_connectors}) "
        f"noise={combined.noise_rate:.3f} ({combined.spurious_connectors}/{combined.inferred_connectors})"
    )
    for accuracy in per_mode:
        print(
            f"mode={accuracy.mode} "
            f"coverage={accuracy.coverage:.3f} "
            f"({accuracy.covered_connectors}/{accuracy.ground_truth_connectors}) "
            f"noise={accuracy.noise_rate:.3f} "
            f"({accuracy.spurious_connectors}/{accuracy.inferred_connectors})"
        )

    assert combined.coverage > 0.0
    assert combined.inferred_connectors > 0
