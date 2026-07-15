import os
from unittest.mock import MagicMock, patch

from src.main import AutoTiler


@patch("src.main.os.makedirs")
@patch("src.main.os.path.exists")
@patch("src.main.open")
def test_load_config_fallback(mock_open, mock_exists, mock_makedirs):
    """Test config falls back to dwindle if layout missing."""
    mock_exists.return_value = False  # No config file exists

    autotiler = AutoTiler(log_enabled=False)

    # Verify default layout chosen is dwindle
    assert autotiler.default_layout == "dwindle"
    mock_makedirs.assert_called()
