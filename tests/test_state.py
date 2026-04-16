import json
from pathlib import Path
import pytest
from ai_loop.state import LoopState, load_state, save_state


class TestLoopState:
    def test_load_from_file(self, ai_loop_dir: Path):
        state = load_state(ai_loop_dir / "state.json")
        assert state.current_round == 1
        assert state.phase == "idle"
        assert state.retry_counts == {"review": 0, "acceptance": 0}
        assert state.history == []

    def test_save_and_reload(self, ai_loop_dir: Path):
        state_file = ai_loop_dir / "state.json"
        state = load_state(state_file)
        state.current_round = 2
        state.phase = "product_explore"
        save_state(state, state_file)

        reloaded = load_state(state_file)
        assert reloaded.current_round == 2
        assert reloaded.phase == "product_explore"

    def test_next_round(self, ai_loop_dir: Path):
        state = load_state(ai_loop_dir / "state.json")
        state.complete_round("Improved login flow")

        assert state.current_round == 2
        assert state.phase == "idle"
        assert state.retry_counts == {"review": 0, "acceptance": 0}
        assert len(state.history) == 1
        assert state.history[0]["round"] == 1
        assert state.history[0]["summary"] == "Improved login flow"

    def test_increment_retry(self, ai_loop_dir: Path):
        state = load_state(ai_loop_dir / "state.json")
        state.increment_retry("review")
        assert state.retry_counts["review"] == 1
        state.increment_retry("review")
        assert state.retry_counts["review"] == 2

    def test_round_dir_path(self, ai_loop_dir: Path):
        state = load_state(ai_loop_dir / "state.json")
        assert state.round_dir(ai_loop_dir) == ai_loop_dir / "rounds" / "001"

    def test_missing_file_creates_default(self, tmp_path: Path):
        state_file = tmp_path / "state.json"
        state = load_state(state_file)
        assert state.current_round == 1
        assert state.phase == "idle"

    def test_ai_loop_version_round_trip(self, tmp_path: Path):
        state_file = tmp_path / "state.json"
        state = LoopState(ai_loop_version="1.2.3")
        save_state(state, state_file)

        reloaded = load_state(state_file)
        assert reloaded.ai_loop_version == "1.2.3"

    def test_ai_loop_version_missing_defaults_empty(self, tmp_path: Path):
        """Old state files without ai_loop_version should load with empty string."""
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "current_round": 3,
            "phase": "idle",
            "retry_counts": {"review": 0, "acceptance": 0},
            "history": [],
        }))

        state = load_state(state_file)
        assert state.ai_loop_version == ""
        assert state.current_round == 3
