# Reducer - Easy Extraction of Code Reduction Tool Runs from Projects

A tool to invoke reduction tools cvise or creduce on C++ files inside of a
project. Handles extraction of the file from the project into a work directory,
and auto-preprocesses the file if the error remains, and tries repeating
pre-processing after convergence of the reduction tool for even smaller
reproducers.

The tool is based on drivers invoked via top-level commands (`tidy`, `compiler-crash`).

Here is an example for a clang-tidy crash (the default for the `tidy` driver):

```sh
reducer.py tidy \
           --build-dir /path/to/problematic/build/ \
           --file /path/to/problematic/file.cpp
```

What this invocation does:

- extract `file.cpp` into a separate working directory
- extract the corresponding compile command from `compile_commands.json`
- get the clang-tidy config for this file and write a `.clang-tidy` config file
  in the working directory
- try to deduce the crashing check from the enabled checks for this file by
  scanning the crash message, and falling back to binary search
- pre-process the file if it retains the error
- set up the interestingness test by first compiling the code with the compiler
  specified in the compilation command, and then calling clang-tidy
- run the interestingness test

The tool can also reduce broken clang-tidy fixes (`--require-post-compile`),
support grepping for false-positives, and timeouts.
