import ctypes
from unittest.mock import MagicMock

import pytest

# Mock windll namespace at the root module level if on Linux/macOS
if not hasattr(ctypes, "windll"):
    mock_windll = MagicMock()
    ctypes.windll = mock_windll


@pytest.fixture(autouse=True)
def mock_win32_system_calls(monkeypatch):
    """Safely replace Win32 DLL loaders with dynamic MagicMocks to bypass Pyright errors."""

    # 1. Create clean mocks
    mock_user32 = MagicMock()
    mock_user32.CreateWindowExW.return_value = 99999
    mock_user32.RegisterClassW.return_value = True
    mock_user32.LoadImageW.return_value = 88888
    mock_user32.DefWindowProcW.return_value = 0

    mock_kernel32 = MagicMock()
    mock_kernel32.GetModuleHandleW.return_value = 11111
    mock_kernel32.GetLastError.return_value = 0

    mock_shell32 = MagicMock()
    mock_shell32.Shell_NotifyIconW.return_value = True

    # 2. Swap DLL loaders dynamically on windll (silences Pyright and ensures safety)
    monkeypatch.setattr(ctypes.windll, "user32", mock_user32)
    monkeypatch.setattr(ctypes.windll, "kernel32", mock_kernel32)
    monkeypatch.setattr(ctypes.windll, "shell32", mock_shell32)

    return ctypes.windll
