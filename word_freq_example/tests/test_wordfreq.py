"""Unit and command-line tests for wordfreq."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from wordfreq import count_words

SCRIPT = Path(__file__).resolve().parents[1] / "wordfreq.py"


class CountWordsTests(unittest.TestCase):
    def test_case_insensitive_counts(self):
        self.assertEqual(count_words("Pear pear PEAR apple"), {"pear": 3, "apple": 1})

    def test_punctuation_separates_words(self):
        self.assertEqual(
            count_words("'pear',apple! pear—APPLE; (banana)."),
            {"pear": 2, "apple": 2, "banana": 1},
        )

    def test_digits_and_underscores_are_separators(self):
        self.assertEqual(count_words("apple_pear123apple"), {"apple": 2, "pear": 1})

    def test_unicode_letters_and_casefolding(self):
        self.assertEqual(
            count_words("CAFÉ café Straße STRASSE"), {"café": 2, "strasse": 2}
        )

    def test_whitespace_and_empty_input(self):
        self.assertEqual(count_words("pear\napple\tpear"), {"pear": 2, "apple": 1})
        for text in ("", " \n\t", "!?---123_"):
            with self.subTest(text=text):
                self.assertEqual(count_words(text), {})


class CommandLineTests(unittest.TestCase):
    def run_cli(self, text, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=text,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_acceptance_example_is_sorted(self):
        result = self.run_cli("Pear pear apple!")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "apple 1\npear 2\n")
        self.assertEqual(result.stderr, "")

    def test_empty_input_prints_nothing(self):
        result = self.run_cli("")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_json_contains_same_counts(self):
        for text in ("Pear pear apple!", "CAFÉ café Straße STRASSE; pear-apple"):
            with self.subTest(text=text):
                result = self.run_cli(text, "--json")
                plain = self.run_cli(text)
                expected = {
                    word: int(count)
                    for word, count in (
                        line.split() for line in plain.stdout.splitlines()
                    )
                }
                self.assertEqual(result.returncode, 0)
                self.assertEqual(plain.returncode, 0)
                self.assertEqual(json.loads(result.stdout), expected)
                self.assertEqual(result.stderr, "")

    def test_empty_json_is_an_object(self):
        result = self.run_cli("", "--json")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})
        self.assertEqual(result.stderr, "")

    def test_unknown_options_fail(self):
        for args in (("--unknown",), ("--json", "--unknown"), ("--js",)):
            with self.subTest(args=args):
                result = self.run_cli("Pear pear apple!", *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("error:", result.stderr)
                self.assertIn(args[-1], result.stderr)

    def test_help(self):
        result = self.run_cli("", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--json", result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
