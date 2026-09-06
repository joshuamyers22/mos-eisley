"""Keep policy independent of provider and filesystem implementation details."""

import ast
from pathlib import Path
from unittest import TestCase

import mos_eisley


class ArchitectureTests(TestCase):
    def test_inner_layers_do_not_import_adapters_or_io(self) -> None:
        root = Path(mos_eisley.__file__).parent
        forbidden = {"os", "subprocess", "socket", "sqlite3", "pathlib", "httpx"}
        for folder in ("core", "review", "evaluation"):
            for path in (root / folder).glob("*.py"):
                for node in ast.walk(ast.parse(path.read_text())):
                    names: list[str] = []
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names = [node.module]
                    for name in names:
                        self.assertNotIn(name.split(".")[0], forbidden, str(path))
                        self.assertFalse(
                            name.startswith(
                                (
                                    "mos_eisley.providers",
                                    "mos_eisley.run",
                                    "mos_eisley.cli",
                                )
                            ),
                            str(path),
                        )
