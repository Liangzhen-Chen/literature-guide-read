"""The plugin manifest names the skill folder and carries the CHANGELOG's version."""
import json

import common


def test_plugin_manifest_matches_skill_and_changelog():
    root = common.SKILL_DIR
    manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == common.skill_version()
    assert manifest["license"] == "MIT"
    for path in manifest["skills"]:
        assert (root / path / "SKILL.md").is_file()
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert [p["name"] for p in market["plugins"]] == [manifest["name"]]
