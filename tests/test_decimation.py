import numpy as np

from evil_sorter.data import minmax_decimate


def test_minmax_decimation_preserves_extrema():
    y = np.sin(np.linspace(0, 40, 10000))
    y[1234] = 9.0
    y[8765] = -8.0
    _, values = minmax_decimate(y, 0, len(y), 500)
    assert 9.0 in values
    assert -8.0 in values
    assert len(values) <= 500

