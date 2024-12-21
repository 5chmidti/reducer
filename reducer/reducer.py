#!/usr/bin/env python

import sys
from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from pathlib import Path
from shutil import which
from uuid import uuid4

from reducer.driver.clang_tidy import ClangTidyDriver
from reducer.lib.log import log
from reducer.lib.setup import (
    load_compile_commands,
    preprocess_file,
    reduce,
)


def init_argparse() -> ArgumentParser:
    parser = ArgumentParser(
        description="Extract and run reductions for cvise/creduce from a"
        " project with compile_commands.json.",
        add_help=False,
    )
    parser.add_argument(
        "--file",
        help="Source file to reduce.",
        type=Path,
        required=False,
    )
    parser.add_argument(
        "--reduce-bin",
        help="Tool to use for reduction (e.g., cvise, creduce).",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--build-dir",
        help="Build directory of project.",
        required=False,
        type=Path,
    )
    parser.add_argument(
        "--interesting-command",
        help="Command satisfying interestingness test properties.",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--compile-error",
        help="Reduce an internal compiler error.",
        default=False,
        required=False,
        type=bool,
        action=BooleanOptionalAction,
    )
    parser.add_argument(
        "--verifying-compiler",
        help="The compiler that checks if the reduced code is still valid.",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--verifying-compiler-args",
        help="Arguments to call the verifying compiler with instead of the"
        " arguments from the crashing compiler.",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--rerun-existing",
        help="Run a reduction on an existing reducer folder.",
        required=False,
        type=Path,
    )
    parser.add_argument(
        "--jobs",
        help="Number of jobs to run with the reducer.",
        required=False,
        type=int,
    )
    parser.add_argument(
        "--timeout",
        help="Timeout for the interestingness command, when timing out is"
        " considered the issue (time-out -> interesting).",
        required=False,
        type=int,
    )
    parser.add_argument(
        "--prompt-rerun",
        help="Prompt to re-run the reduction in the created folder. Useful"
        "for manual reductions when the reduction tool can't progress further.",
        default=True,
        required=False,
        type=bool,
        action=BooleanOptionalAction,
    )
    return parser


def set_reduce_bin(args: Namespace) -> None:
    if args.reduce_bin:
        return

    if which("cvise"):
        args.reduce_bin = "cvise"
        return

    if which("creduce"):
        args.reduce_bin = "creduce"
        return

    raise RuntimeError("Could not find reduction binaries 'cvise' or 'creduce'")


def main() -> None:
    common_parser = init_argparse()
    parser = ArgumentParser(description="")
    sub_parser = parser.add_subparsers(
        title="Sub-commands",
    )
    ClangTidyDriver().add_arguments(common_parser, sub_parser)
    args = parser.parse_args()

    if args.compile_error and not args.verifying_compiler:
        log.error("option --compile-error requires --verifying-compiler")
        return

    if args.verifying_compiler_args and not args.verifying_compiler:
        log.error(
            "option --verifying-compiler-args requires --verifying-compiler",
        )
        return

    log.info(f"{args}")

    set_reduce_bin(args)

    if args.rerun_existing:
        cwd = args.rerun_existing

        if not cwd.exists():
            log.error(f"path of rerun_existing does not exist: {cwd}")
            return

        compile_commands = load_compile_commands(cwd)
        compile_command: str = compile_commands[0]["command"]
        file_path: Path = compile_commands[0]["file"]
        preprocess_file(cwd, file_path, compile_command)
    else:
        if not args.file:
            log.error("Needs a '--file=<file>' to reduce")
            sys.exit(1)
        if not args.build_dir:
            log.error(
                "Needs a '--build-dir=<build-dir>' to extract compilation command from",
            )
            sys.exit(1)
        args.file = args.file.resolve()
        args.build_dir = args.build_dir.resolve()

        cwd = args.build_dir / ("reducer/" + str(uuid4().hex))
        cwd.mkdir(exist_ok=True, parents=True)

    log.info(args)
    driver = ClangTidyDriver()
    driver.setup(args, cwd)
    reduce(args, cwd)


if __name__ == "__main__":
    main()
