from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def _run_settings_migration(expression: str) -> object:
    script = f"""
import {{ migrateStoredResponsesSettings }} from './static/responses-settings.mjs'
console.log(JSON.stringify({expression}))
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_v2_legacy_model_is_migrated_again_without_losing_other_settings() -> None:
    result = _run_settings_migration(
        "migrateStoredResponsesSettings({"
        "responsesModel: 'gpt-5.5', responsesModelStorageVersion: 2, imageTransport: 'responses'"
        "}, 'gpt-5.6-sol')"
    )

    assert result == {
        "responsesModel": "gpt-5.6-sol",
        "responsesModelStorageVersion": 3,
        "imageTransport": "responses",
    }


def test_v3_manual_legacy_model_selection_is_not_repeatedly_overwritten() -> None:
    result = _run_settings_migration(
        "(() => {"
        "const settings = { responsesModel: 'gpt-5.5', responsesModelStorageVersion: 3 };"
        "const migrated = migrateStoredResponsesSettings(settings, 'gpt-5.6-sol');"
        "return { sameObject: migrated === settings, migrated };"
        "})()"
    )

    assert result == {
        "sameObject": True,
        "migrated": {"responsesModel": "gpt-5.5", "responsesModelStorageVersion": 3},
    }


def test_v2_custom_model_is_preserved_while_advancing_storage_version() -> None:
    result = _run_settings_migration(
        "migrateStoredResponsesSettings({"
        "responsesModel: 'custom-image-model', responsesModelStorageVersion: 2"
        "}, 'gpt-5.6-sol')"
    )

    assert result == {
        "responsesModel": "custom-image-model",
        "responsesModelStorageVersion": 3,
    }
