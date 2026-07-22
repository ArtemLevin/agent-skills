from __future__ import annotations

import json
import unittest
from pathlib import Path


class QualitySchemaTests(unittest.TestCase):
    def test_quality_schemas_are_valid_json(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for name in (
            "quality-snapshot.schema.json",
            "quality-hotspots.schema.json",
            "quality-provider.schema.json",
        ):
            payload = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(payload["type"], "object")


if __name__ == "__main__":
    unittest.main()
