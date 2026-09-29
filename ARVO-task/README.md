# Fluent Bit unit tests in ARVO image `n132/arvo:51132-fix`

This artifact runs the unit tests that ship with Fluent Bit inside the ARVO image
for OSS-Fuzz issue 51132 (Fluent Bit at fix commit `e2c524b`, "parser: fix
double-free"), and measures their code coverage.

The artifact is one script, `run_tests.sh`.

## Requirements

- An **x86-64** machine with Docker. On Apple Silicon (ARM) machines, I encountered some issues while running the tests.
- Internet access from the container (the script installs packages with apt).

## 1. Start the container

```bash
docker pull n132/arvo:51132-fix
docker run -it --name arvo_51132_demo n132/arvo:51132-fix bash
```

Use a fresh container: the script edits and builds inside `/src/fluent-bit`.

## 2. Copy the script into the container

In a second terminal on the host:

```bash
docker cp run_arvo_51132.sh arvo_51132_demo:/run_arvo_51132.sh
```

## 3. Run it

Inside the container:

```bash
bash /run_arvo_51132.sh
```

The script:

1. installs the build tools and the coverage tools (gcc, gcovr);
2. moves the expiry dates of the fake AWS credentials in two tests from 2025
   to 3025;
3. builds Fluent Bit with its internal unit tests and coverage instrumentation;
4. runs all unit tests with CTest;
5. writes a coverage report for Fluent Bit's own code (`src/` and `plugins/`).

The build takes less than a 30 seconds on 6x Intel Xeon E-2134.

## 4. Results

**Tests.** The CTest summary shows how many of the 46 unit tests passed, e.g.
`100% tests passed, 0 tests failed out of 46`. The script exits with 0 if all
tests passed and 1 otherwise.

**Coverage.** The summary is printed at the end, e.g.

```
lines: 21.2% (12911 out of 60760)
branches: 16.1% (5626 out of 34990)
```

The HTML report is in `/src/fluent-bit/build/coverage/index.html`. Copy it to
the host and open `index.html` in a browser:

```bash
docker cp arvo_51132_demo:/src/fluent-bit/build/coverage ./coverage
```

## Notes

- **AWS credential tests.** `flb-it-aws_credentials_http` and
  `flb-it-aws_credentials_sts` contain fake credentials that expired in
  October/November 2025, so they fail on today's date regardless of the code.
  The script moves those dates to 3025 before building; only test data
  changes, and upstream fixed the same issue in commit `f879a93bc`.
- **Build options.** The image exports compiler flags meant for the fuzzer
  build; the script unsets them. It also switches off parts the tests don't
  need (the `fluent-bit` program, shared library, examples, backtrace library).
  With them on, linking the program fails with a gcc PIE relocation error.