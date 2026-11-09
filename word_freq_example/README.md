# wordfreq

A small standard-library Python program that reads standard input and prints
case-insensitive word counts in alphabetical order. Requires Python 3.12 or newer;
no installation or dependencies are needed.

```sh
printf 'Pear pear apple!' | python wordfreq.py
```

Output:

```text
apple 1
pear 2
```

Read a UTF-8 text file using shell redirection (with a UTF-8 terminal environment):

```sh
python wordfreq.py < notes.txt
```

Words are runs of Unicode letters. Punctuation, digits, underscores, and whitespace
separate words; for example, `pear-apple` counts as `pear` and `apple`. Unicode
case folding makes matching case-insensitive. Empty input produces no output.

Use `--json` to print the same counts as a JSON object with alphabetically sorted
keys:

```sh
printf 'Pear pear apple!' | python wordfreq.py --json
```

```json
{"apple": 1, "pear": 2}
```

Empty input with `--json` produces `{}`. Run `python wordfreq.py --help` for
available options. Unknown options exit non-zero and print an error to stderr.

Run the automated tests from the repository root:

```sh
python -m unittest discover -s tests -v
```
