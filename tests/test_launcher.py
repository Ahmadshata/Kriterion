import os
import subprocess
import unittest
from pathlib import Path


class KriterionLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.launcher = cls.root / "kriterion.sh"
        cls.screening_script = cls.root / "kriterion.py"

    def invoke(self, *arguments: str) -> list[str]:
        environment = dict(os.environ)
        environment["KRITERION_PYTHON"] = "/bin/echo"
        result = subprocess.run(
            [str(self.launcher), *arguments],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip().split()

    def test_defaults_are_non_interactive_and_explicit(self) -> None:
        self.assertEqual(
            self.invoke(),
            [
                str(self.screening_script),
                "./cvs",
                "--profile",
                "./profiles/profile.yaml",
                "--output-dir",
                ".",
            ],
        )

    def test_path_flags_and_extra_options_are_forwarded(self) -> None:
        self.assertEqual(
            self.invoke(
                "--cvs-dir",
                "./batch",
                "--profile=./profiles/backend.yaml",
                "--output-dir",
                "./reports",
                "--no-open",
                "--no-cache",
                "--min-score",
                "80",
            ),
            [
                str(self.screening_script),
                "./batch",
                "--profile",
                "./profiles/backend.yaml",
                "--output-dir",
                "./reports",
                "--no-open",
                "--no-cache",
                "--min-score",
                "80",
            ],
        )

    def test_no_cache_is_forwarded_to_the_screening_cli(self) -> None:
        self.assertEqual(
            self.invoke("--no-cache"),
            [
                str(self.screening_script),
                "./cvs",
                "--profile",
                "./profiles/profile.yaml",
                "--output-dir",
                ".",
                "--no-cache",
            ],
        )


if __name__ == "__main__":
    unittest.main()
