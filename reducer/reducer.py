#!/usr/bin/env python

import sys
from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from pathlib import Path
from shutil import which
from uuid import uuid4

from reducer.driver.clang_tidy import ClangTidyDriver
from reducer.driver.compiler_crash import CompilerCrashDriver
from reducer.lib.driver import Driver
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
        " for manual reductions when the reduction tool can't progress further.",
        default=True,
        required=False,
        type=bool,
        action=BooleanOptionalAction,
    )
    parser.add_argument(
        "--crash",
        help="If the case to reduce crashes the program",
        default=True,
        type=bool,
        action=BooleanOptionalAction,
        required=False,
    )
    parser.add_argument(
        "--grep",
        help="A regex to search for in all outputs",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--grep-file",
        help="A regex to search for in the file being reduced",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--extra-args",
        help="Extra arguments to append to the compilation command",
        required=False,
        type=str,
        default="",
    )
    parser.add_argument(
        "--repeat",
        help="Repeat the main part of the interestingness test",
        type=int,
        required=False,
        default=1,
    )
    return parser


def set_reduce_bin(args: Namespace) -> None:
    if args.reduce_bin:
        if which(args.reduce_bin):
            return
        log.error(f"Could not find reduction binary '{args.reduce_bin}'")
        sys.exit(1)

    if which("cvise"):
        args.reduce_bin = "cvise"
        return

    if which("creduce"):
        args.reduce_bin = "creduce"
        return

    log.error("Could not find reduction binaries 'cvise' or 'creduce'")
    sys.exit(1)


def main() -> None:
    common_parser = init_argparse()
    parser = ArgumentParser(description="")
    sub_parser = parser.add_subparsers(
        title="Sub-commands",
        dest="sub",
    )
    ClangTidyDriver.add_arguments(common_parser, sub_parser)
    CompilerCrashDriver.add_arguments(common_parser, sub_parser)
    args = parser.parse_args()

    log.info(args)

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

    driver: Driver | None = None
    match args.sub:
        case "tidy":
            driver = ClangTidyDriver(args, cwd)
        case "compiler-crash":
            driver = CompilerCrashDriver(args, cwd)

    if driver is None:
        return

    reduce(args, cwd)


if __name__ == "__main__":
    main()
