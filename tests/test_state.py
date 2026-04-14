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
