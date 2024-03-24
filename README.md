# Reducer - Easy Extraction of Code Reduction Tool Runs from Projects

```console
$ python -m venv ./venv
$ source venv/bin/activate.fish # or whichever shell you use
$ pip install -r requirements.txt
$ pytest test/test_reducer.py

# Reduce main.cpp such that invoking it still prints Hello World.
python reducer/reducer.py --build-dir /path/to/project/build/ --interesting-command "./bin/my_app | grep -I 'Hello World'" /path/to/project/src/main.cpp
```

This tool allows for easy extraction of files needed for a reduction and runs the reduction with the specified reduction tool (e.g., cvise).

For each reduction (invoking this script), this tool creates a folder inside `/path/to/project/build/reducer/<uuid>` and places all files required for the reduction inside that folder.
This keeps different reductions separate and available for modification, should the interestingness test not be correct, or you want to apply some manual reductions.

To re-run reductions on an existing folder use `--rerun-existing`, which can be used to preprocess the source file after some initial iteration has been done.

The `--interesting-command` argument follows the conventions of `creduce` and `cvise` and you can use log.txt to access the compile log.
For the interestingness test to work correctly, the path of the source file (if mentioned) has to be fully written out like it was passed as the positional argument, because the tool replaces the paths to the source file to the location in the directory created for the reduction.

Checkout [test/test_reducer.py](test_reducer.py) for examples that include a reduction with clang-tidy, an internal compiler error and grep.

```console
$ python reducer/reducer.py

usage: reducer.py [-h] [--reduce-bin REDUCE_BIN] [--build-dir BUILD_DIR] [--interesting-command INTERESTING_COMMAND] [--compile-error | --no-compile-error] [--verifying-compiler VERIFYING_COMPILER] [--verifying-compiler-args VERIFYING_COMPILER_ARGS] [--preprocess | --no-preprocess]
                  [--rerun-existing RERUN_EXISTING] [--jobs JOBS] [--timeout TIMEOUT]
                  source_file

Extract and run reductions for cvise/creduce from a project with compile_commands.json.

positional arguments:
  source_file           Source file to reduce.

options:
  -h, --help            show this help message and exit
  --reduce-bin REDUCE_BIN
                        Tool to use for reduction (e.g., cvise, creduce).
  --build-dir BUILD_DIR
                        Build directory of project.
  --interesting-command INTERESTING_COMMAND
                        Command satisfying interestingness test properties.
  --compile-error, --no-compile-error
                        Reduce an internal compiler error.
  --verifying-compiler VERIFYING_COMPILER
                        The compiler that checks if the reduced code is still valid.
  --verifying-compiler-args VERIFYING_COMPILER_ARGS
                        Arguments to call the verifying compiler with instead of the arguments from the crashing compiler. Use $FILE to reference the source file.
  --preprocess, --no-preprocess
                        Run preprocessor on source file.
  --rerun-existing RERUN_EXISTING
                        Run a reduction on an existing reducer folder.
  --jobs JOBS           Number of jobs to run with the reducer.
  --timeout TIMEOUT     Timeout for the interestingness command, when timing out is considered the issue (time-out -> interesting).
```
