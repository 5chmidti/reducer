#!/usr/bin/env python

import json
import logging
import re
from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from multiprocessing import cpu_count
from pathlib import Path
from shutil import copy, which
from stat import S_IEXEC
from subprocess import call, run
from typing import Any
from uuid import uuid4

from rich.logging import RichHandler

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO",
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler()],
)

log = logging.getLogger("rich")


def init_argparse() -> ArgumentParser:
    parser = ArgumentParser(
        description="Extract and run reductions for cvise/creduce from a"
        " project with compile_commands.json.",
    )
    parser.add_argument(
        "source_file",
        help="Source file to reduce.",
        type=Path,
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


def replace_path(string: str, file: Path, new_path_str: str) -> str:
    return (
        string.replace(str(file), new_path_str)
        .replace(str(file.absolute()), new_path_str)
        .replace(str(file.resolve()), new_path_str)
    )


def transform_compile_commands(comp_db_entry: str, source_file: Path) -> str:
    comp_db_entry = replace_path(comp_db_entry, source_file, source_file.name)
    comp_db_entry = re.sub(r"-o [^ ]*\.o", "-o output.cpp.o", comp_db_entry)
    comp_db_entry = comp_db_entry.replace("-c ", f"-I{source_file.parent} -c ")
    comp_db_entry = comp_db_entry.replace("-c ", "-Wfatal-errors -c ")
    return re.sub(r"-Werror(=[\w-]*)?", "", comp_db_entry)


def get_compile_commands_entry_for_file(  # noqa: ANN201
    source_file: Path,
    build_dir: Path,
):
    compile_commands_file = build_dir / "compile_commands.json"
    raw_commands = transform_compile_commands(
        compile_commands_file.read_text(),
        source_file,
    )

    return [x for x in json.loads(raw_commands) if source_file.name in x["file"]]


def remove_explicit_path(compile_command: str, cwd: Path) -> str:
    return compile_command.replace(str(cwd) + "/", "")


def write_compile_commands(compile_commands: Any, cwd: Path) -> None:
    (cwd.absolute() / "compile_commands.json").write_text(json.dumps(compile_commands))


def create_interestingness_test(
    args: Namespace,
    cwd: Path,
    compile_command: str,
) -> None:
    compile_command = remove_explicit_path(compile_command, cwd)

    file = Path(f"{cwd}/test.sh")
    file_content: str = "#!/bin/bash\n"

    if args.compile_error and args.verifying_compiler:
        verifying_compiler_args: str
        if args.verifying_compiler_args:
            verifying_compiler_args = args.verifying_compiler_args
        else:
            verifying_compiler_args = (
                compile_command[compile_command.find(" ") :]
                .replace("-fcolor-diagnostics", "")
                .replace("-Wdocumentation", "")
                .replace("-fopenmp=libomp", "-fopenmp")
            )
        file_content = str(
            file_content
            + str(args.verifying_compiler)
            + f" {verifying_compiler_args} && ",
        )

    if args.compile_error and args.timeout:
        file_content = file_content + f"! timeout {args.timeout} "
    file_content = str(
        file_content
        + compile_command
        + " -Wfatal-errors -fno-color-diagnostics > log.txt 2>&1",
    )

    if args.interesting_command:
        interesting_command = replace_path(
            args.interesting_command,
            args.source_file,
            args.source_file.name,
        )
        interesting_command = re.sub(
            r"-p[ =]?[^ ]*",
            f"-p {cwd!s}",
            interesting_command,
        )
        log.info(f"interesting_command: {interesting_command}")

        file_content = file_content + " &&"
        if args.timeout:
            file_content = file_content + f" ! timeout {args.timeout}"
        file_content = str(
            file_content + f" {interesting_command}\n",
        )

    file.write_text(file_content)
    file.chmod(file.stat().st_mode | S_IEXEC)


def setup_test_folder(args: Namespace, cwd: Path) -> None:
    compile_commands = get_compile_commands_entry_for_file(
        args.source_file,
        args.build_dir,
    )
    write_compile_commands(compile_commands, cwd)
    file_path: Path = args.source_file
    copy(file_path, cwd / file_path.name)
    compile_command = compile_commands[0]["command"]

    create_interestingness_test(args, cwd, compile_command)
    preprocess_file(cwd, file_path, compile_command)


def preprocess_file(cwd: Path, file_path: Path, compile_command: str) -> None:
    copy(f"{cwd / file_path.name}", f"{cwd / file_path.name}.bckp")

    c = compile_command.replace(
        "-o output.cpp.o",
        f"-E -P -o {cwd / file_path.name}",
    ).split(" ")

    log.info(f"preprocess: {' '.join(c)}")

    call(c, cwd=cwd)
    if call(["sh", "test.sh"], cwd=cwd) != 0:
        log.info("preprocessing the file did not retain the same error")

        copy(f"{cwd / file_path.name}.bckp", f"{cwd / file_path.name}")


def load_compile_commands(build_dir: Path) -> Any:
    compile_commands_file = build_dir / "compile_commands.json"
    compile_commands_raw = compile_commands_file.read_text()
    return json.loads(compile_commands_raw)


def get_cpp_std_from_compile_commands(cwd: Path) -> str:
    cpp_std = "c++20"
    compile_commands = load_compile_commands(cwd)
    compile_command: str = compile_commands[0]["command"]
    cpp_std_pos = compile_command.find("-std=")
    if cpp_std_pos != -1:
        is_gnu = compile_command[cpp_std_pos + 5] == "g"
        if is_gnu:
            cpp_std = f"c++{compile_command[cpp_std_pos + 10 : cpp_std_pos + 12]}"
        else:
            cpp_std = f"{compile_command[cpp_std_pos + 6 : cpp_std_pos + 11]}"
    return cpp_std


def get_csvise_supported_cpp_std(args: Namespace, cpp_std: str) -> str:
    res = run([args.reduce_bin, "--help"], capture_output=True, check=False)
    help_msg = res.stdout.decode()

    clang_delta_std_flag = "--clang-delta-std {"
    clang_delta_std_loc = help_msg.find(clang_delta_std_flag) + len(
        clang_delta_std_flag,
    )

    help_msg = help_msg[
        clang_delta_std_loc : help_msg.find("}", clang_delta_std_loc + 1)
    ]

    if cpp_std in help_msg:
        return cpp_std

    res = help_msg.split(",")[-1]
    if res != "":
        return res

    return "c++20"


def reduce_input(args: Namespace, cwd: Path) -> None:
    invocation: list[str] = [args.reduce_bin]

    if "cvise" in args.reduce_bin:
        invocation.append(
            f"--clang-delta-std={get_csvise_supported_cpp_std(args, get_cpp_std_from_compile_commands(cwd))}",
        )
        invocation.append("--to-utf8")

    if args.jobs:
        invocation.append(f"--n={args.jobs}")
    else:
        invocation.append(f"--n={cpu_count()}")

    if args.timeout:
        invocation.append(f"--timeout={args.timeout}")

    invocation.append("test.sh")
    invocation.append(args.source_file.name)

    log.info(invocation)

    return_code = call(invocation, cwd=cwd)
    if return_code != 0:
        raise RuntimeError("reduction invokation failed")


def reduce_existing(args: Namespace) -> None:
    set_reduce_bin(args)

    existing_path = args.rerun_existing

    if not existing_path.exists():
        log.error(f"path of rerun_existing does not exist: {existing_path}")
        return

    compile_commands = load_compile_commands(existing_path)
    compile_command: str = compile_commands[0]["command"]
    file_path: Path = compile_commands[0]["file"]
    preprocess_file(existing_path, file_path, compile_command)

    reduce_input(args, existing_path)


def reduce_new(args: Namespace) -> None:
    set_reduce_bin(args)

    args.source_file = args.source_file.resolve()
    args.build_dir = args.build_dir.resolve()

    cwd = args.build_dir / ("reducer/" + str(uuid4().hex))
    cwd.mkdir(exist_ok=True, parents=True)

    if args.interesting_command:
        args.interesting_command = replace_path(
            args.interesting_command,
            args.build_dir,
            str(cwd),
        )

    setup_test_folder(args, cwd)
    reduce_input(args, cwd)


def main() -> None:
    parser = init_argparse()
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

    if args.rerun_existing:
        reduce_existing(args)
    else:
        reduce_new(args)


if __name__ == "__main__":
    main()
