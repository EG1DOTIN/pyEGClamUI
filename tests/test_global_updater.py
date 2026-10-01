"""
Unit tests for GlobalUpdatePipeline.
"""

from unittest.mock import MagicMock, patch
import pytest

from pyegclamui.core.updater import GlobalUpdatePipeline, ClamUpdater


def test_global_update_pipeline_stages():
    mock_clam_updater = MagicMock(spec=ClamUpdater)
    mock_clam_updater.detector = MagicMock()
    mock_clam_updater.detector.get_engine_version.return_value = {"clamav_version": "1.4.1"}
    mock_clam_updater.run_update.return_value = (True, "Signatures up to date")

    pipeline = GlobalUpdatePipeline(clam_updater=mock_clam_updater)

    stages = []
    logs = []
    progress_vals = []

    def on_stage(current, total, title):
        stages.append((current, total, title))

    def on_log(line):
        logs.append(line)

    def on_progress(p):
        progress_vals.append(p)

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = ["Already up to date.\n", ""]
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        success, summary, code_updated = pipeline.run_pipeline(
            on_stage=on_stage,
            on_log=on_log,
            on_progress=on_progress,
        )

        assert success is True
        assert len(stages) == 4
        assert any(p == 100 for p in progress_vals)
        assert any("App Code" in s for s in summary.split("\n"))
        assert any("Signatures" in s for s in summary.split("\n"))


def test_global_update_pipeline_cancel():
    mock_clam_updater = MagicMock()
    mock_clam_updater.detector = MagicMock()
    pipeline = GlobalUpdatePipeline(clam_updater=mock_clam_updater)
    pipeline.cancel()
    assert pipeline._cancelled is True
