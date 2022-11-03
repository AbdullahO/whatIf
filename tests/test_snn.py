import os
from typing import Tuple

import networkx as nx
import numpy as np
import pandas as pd
import pytest
from numpy import ndarray

from algorithms.snn import SNN

current_dir = os.getcwd()


@pytest.fixture(scope="session")
def expected_anchor_rows() -> ndarray:
    # fmt: off
    anchor_rows = np.array([
        1,  2,  4,  9, 11, 16, 18, 19, 24, 25, 32, 33, 34, 37, 38, 49, 50,
       56, 57, 58, 59, 60, 63, 65, 67, 68, 80, 82, 84, 87, 90, 92, 96, 97,
       99
    ])
    # fmt: on
    return anchor_rows


@pytest.fixture(scope="session")
def expected_anchor_cols() -> ndarray:
    anchor_cols = np.array([0, 3, 6, 9, 12, 15, 18, 21, 24, 27])
    return anchor_cols


@pytest.fixture(scope="session")
def snn_model() -> SNN:
    _snn_test_df = pd.read_csv(
        os.path.join(current_dir, "data/stores_sales_simple/stores_sales_simple.csv")
    )
    model = SNN(verbose=False)
    model.fit(
        df=_snn_test_df,
        unit_column="unit_id",
        time_column="time",
        metrics=["sales"],
        actions=["ads"],
    )
    return model


@pytest.fixture(scope="session")
def snn_model_matrix(snn_model: SNN) -> ndarray:
    X = snn_model.matrix
    assert X is not None
    return X


@pytest.fixture(scope="session")
def snn_model_matrix_full(snn_model: SNN) -> ndarray:
    X_full = snn_model.matrix_full
    assert X_full is not None
    return X_full


@pytest.fixture(scope="session")
def missing_set(snn_model_matrix: ndarray) -> ndarray:
    X = snn_model_matrix
    missing_set = np.argwhere(np.isnan(X))
    missing_row, missing_col = missing_set[0]
    assert np.isnan(X[missing_row, missing_col]), "first missing pair is not missing"
    return missing_set


@pytest.fixture(scope="session")
def example_missing_pair(missing_set: ndarray) -> ndarray:
    # Pick 20th missing pair because it has the first feasible output
    return missing_set[20]


@pytest.fixture(scope="session")
def example_obs_rows_and_cols(
    snn_model_matrix: ndarray, example_missing_pair: ndarray
) -> Tuple[frozenset, frozenset]:
    X = snn_model_matrix
    missing_row, missing_col = example_missing_pair
    example_obs_rows = frozenset(np.argwhere(~np.isnan(X[:, missing_col])).flatten())
    example_obs_cols = frozenset(np.argwhere(~np.isnan(X[missing_row, :])).flatten())
    return example_obs_rows, example_obs_cols


def test_predict(
    snn_model: SNN, snn_model_matrix: ndarray, example_missing_pair: ndarray
):
    """Test the _predict function"""
    prediction, feasible = snn_model._predict(snn_model_matrix, example_missing_pair)
    assert feasible, "prediction not feasible"
    assert prediction.round(6) == 48407.449874, "prediction has changed"


@pytest.mark.parametrize("k", [2, 4, 5])
def test_split(snn_model: SNN, expected_anchor_rows: ndarray, k: int):
    anchor_rows_splits = list(snn_model._split(expected_anchor_rows, k=k))
    quotient, remainder = divmod(len(expected_anchor_rows), k)
    assert len(anchor_rows_splits) == k, "wrong number of splits"
    for idx, split in enumerate(anchor_rows_splits):
        expected_len = quotient + 1 if idx < remainder else quotient
        assert len(split) == expected_len


def test_model_repr(snn_model: SNN):
    assert str(snn_model) == (
        "SNN(linear_span_eps=0.1, max_rank=None, max_value=None,"
        " metric='sales', min_singular_value=1e-07, min_value=None,"
        " n_neighbors=1, random_splits=False, spectral_t=None, subspace_eps=0.1,"
        " verbose=False, weights='uniform')"
    )


def test_find_max_clique(
    snn_model_matrix: ndarray, example_obs_rows_and_cols: Tuple[frozenset, frozenset]
):
    obs_rows, obs_cols = example_obs_rows_and_cols
    _obs_rows = np.array(list(obs_rows), dtype=int)
    _obs_cols = np.array(list(obs_cols), dtype=int)

    # create bipartite incidence matrix
    X = snn_model_matrix
    B = X[_obs_rows]
    B = B[:, _obs_cols]
    assert np.any(np.isnan(B)), "B already fully connected"
    B[np.isnan(B)] = 0
    (n_rows, n_cols) = B.shape

    row_block_size = (n_rows, n_rows)
    col_block_size = (n_cols, n_cols)

    # No connections (all missing)
    A = np.block(
        [
            [np.ones(row_block_size), np.zeros_like(B)],
            [np.zeros_like(B.T), np.ones(col_block_size)],
        ]
    )
    G = nx.from_numpy_array(A)
    max_clique_rows_idx, max_clique_cols_idx = SNN._find_max_clique(G, n_rows)
    error_message = "Should return False for no clique"
    assert max_clique_rows_idx is False, error_message
    assert max_clique_cols_idx is False, error_message

    # real bipartite graph
    A = np.block([[np.ones(row_block_size), B], [B.T, np.ones(col_block_size)]])
    G = nx.from_numpy_array(A)
    max_clique_rows_idx, max_clique_cols_idx = SNN._find_max_clique(G, n_rows)
    error_message = "Should return ndarray"
    assert isinstance(max_clique_rows_idx, ndarray), error_message
    assert isinstance(max_clique_cols_idx, ndarray), error_message
    assert max_clique_rows_idx.shape == (35,)
    assert max_clique_cols_idx.shape == (10,)

    # Fully connected (none missing)
    A = np.block(
        [
            [np.ones(row_block_size), np.ones_like(B)],
            [np.ones_like(B.T), np.ones(col_block_size)],
        ]
    )
    G = nx.from_numpy_array(A)
    max_clique_rows_idx, max_clique_cols_idx = SNN._find_max_clique(G, n_rows)
    error_message = "Should return ndarray"
    assert isinstance(max_clique_rows_idx, ndarray), error_message
    assert isinstance(max_clique_cols_idx, ndarray), error_message
    assert max_clique_rows_idx.shape == (35,)
    assert max_clique_cols_idx.shape == (50,)
    # _obs_cols.shape == (50,)


def test_get_anchors(
    snn_model: SNN,
    snn_model_matrix: ndarray,
    snn_model_matrix_full: ndarray,
    example_obs_rows_and_cols: ndarray,
    expected_anchor_rows: ndarray,
    expected_anchor_cols: ndarray,
):
    """Test the _get_anchors function"""
    snn_model._get_anchors.cache.clear()
    obs_rows, obs_cols = example_obs_rows_and_cols
    anchor_rows, anchor_cols = snn_model._get_anchors(
        snn_model_matrix, obs_rows, obs_cols
    )

    error_message = "Anchor rows not as expected"
    assert np.allclose(anchor_rows, expected_anchor_rows), error_message
    error_message = "Anchor columns not as expected"
    assert np.allclose(anchor_cols, expected_anchor_cols), error_message

    _obs_rows = np.array(list(obs_rows), dtype=int)
    _obs_cols = np.array(list(obs_cols), dtype=int)
    B = snn_model_matrix_full[_obs_rows]
    B = B[:, _obs_cols]
    assert not np.any(np.isnan(B)), "snn_model_matrix_full contains NaN"

    # Test matrix_full, which should short circuit and return the input
    snn_model._get_anchors.cache.clear()
    anchor_rows, anchor_cols = snn_model._get_anchors(
        snn_model_matrix_full, obs_rows, obs_cols
    )

    error_message = "Anchor rows not as expected"
    assert np.allclose(anchor_rows, _obs_rows), error_message
    error_message = "Anchor columns not as expected"
    assert np.allclose(anchor_cols, _obs_cols), error_message


def test_find_anchors(
    snn_model: SNN,
    snn_model_matrix: ndarray,
    example_missing_pair: ndarray,
    expected_anchor_rows: ndarray,
    expected_anchor_cols: ndarray,
):
    """Test the _find_anchors function"""
    snn_model._get_anchors.cache.clear()
    anchor_rows, anchor_cols = snn_model._find_anchors(
        snn_model_matrix, example_missing_pair
    )

    error_message = "Anchor rows not as expected"
    assert np.allclose(anchor_rows, expected_anchor_rows), error_message
    error_message = "Anchor columns not as expected"
    assert np.allclose(anchor_cols, expected_anchor_cols), error_message


def test_spectral_rank():
    """Test the _spectral_rank function"""


def test_universal_rank():
    """Test the _universal_rank function"""


def test_pcr():
    """Test the _pcr function"""


def test_clip():
    """Test the _clip function"""


def test_train_error():
    """Test the _train_error function"""


def test_get_beta():
    """Test the _get_beta function"""


def test_synth_neighbor():
    """Test the _synth_neighbor function"""


def test_get_tensor():
    """Test the _get_tensor function"""


def test_check_input_matrix():
    """Test the _check_input_matrix function"""


def test_prepare_input_data():
    """Test the _prepare_input_data function"""


def test_check_weights():
    """Test the _check_weights function"""
