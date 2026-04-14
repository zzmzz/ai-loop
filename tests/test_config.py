from pathlib import Path
import yaml
import pytest
from ai_loop.config import AiLoopConfig, load_config


class TestLoadConfig:
    def test_loads_valid_config(self, tmp_path: Path, sample_config: dict):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(sample_config))

        cfg = load_config(config_file)

        assert cfg.project.name == "test-project"
        assert cfg.project.description == "A test project"
        assert cfg.goals == ["Improve the UI"]
        assert cfg.server.start_command == "npm start"
        assert cfg.server.health_timeout == 30
        assert cfg.browser.base_url == "http://localhost:3000"
        assert cfg.limits.max_review_retries == 3

    def test_missing_required_field_raises(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"project": {"name": "x"}}))

        with pytest.raises(ValueError, match="project.path"):
            load_config(config_file)

    def test_file_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "missing.yaml")

    def test_defaults_for_optional_fields(self, tmp_path: Path, sample_config: dict):
        del sample_config["limits"]
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(sample_config))

        cfg = load_config(config_file)

        assert cfg.limits.max_review_retries == 3
        assert cfg.limits.max_acceptance_retries == 2
