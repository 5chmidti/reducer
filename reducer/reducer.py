from argparse import ArgumentParser, Namespace, BooleanOptionalAction
import json
from os import chmod, stat
import re
from shutil import copy, which
from stat import S_IEXEC
from subprocess import call, run
from typing import Any
from uuid import uuid4
from rich.logging import RichHandler
import logging
from pathlib import Path
from multiprocessing import cpu_count


FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

log = logging.getLogger("rich")


def init_argparse() -> ArgumentParser:
    parser = ArgumentParser(
        description="run csmith on get-me executable",
    )
    parser.add_argument(
        "source_file",
        help="source file to reduce",
        type=Path,
    )
    parser.add_argument(
        "--reduce-bin",
        help="binary to use for reduction",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--build-dir",
        help="build directory of project",
        required=False,
        type=Path,
    )
    parser.add_argument(
        "--interesting-command",
        help="command satisfying interestingness test properties",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--compile-error",
        help="build is the interesting command",
        default=False,
        required=False,
        type=bool,
        action=BooleanOptionalAction,
    )
    parser.add_argument(
        "--verifying-compiler",
        help="compiler that checks if the reduced code is still correct",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--verifying-compiler-args",
        help="arguments to call the verifying compiler with instead of the arguments from the crashing compiler. use $FILE to reference the source file",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--preprocess",
        help="run preprocessor on source file",
        action=BooleanOptionalAction,
        default=False,
        required=False,
        type=bool,
    )
    parser.add_argument(
        "--rerun-existing",
        help="run a reduction on an existing reducer folder",
        required=False,
        type=Path,
    )
    parser.add_argument(
        "--jobs",
        help="number of jobs to run with the reducer",
        required=False,
        type=int,
    )
    parser.add_argument(
        "--timeout",
        help="timeout for the interestingness command",
        required=False,
        type=int,
    )
    return parser


def set_reduce_bin(args: Namespace):
    if args.reduce_bin:
        return

    if which("cvise"):
        args.reduce_bin = "cvise"
        return

    if which("creduce"):
        args.reduce_bin = "creduce"
        return

    raise RuntimeError("Could not find reduction binaries cvise or creduce")


def get_compile_commands_entry_for_file(source_file: Path, build_dir: Path, cwd: Path):
    compile_commands_file = build_dir / "compile_commands.json"
    new_file_path = cwd.absolute() / source_file.name
    log.info(str(new_file_path))
    raw_commands = compile_commands_file.read_text()
    raw_commands = raw_commands.replace(str(source_file), "$FILE")
    raw_commands = re.sub(r"-o [^ ]*\.o", "-o output.cpp.o", raw_commands)
    raw_commands = raw_commands.replace("-c ", f"-I{source_file.parent} -c ")
    raw_commands = raw_commands.replace(
        "-c ", "-Wfatal-errors -Wno-invalid-constexpr -c "
    )
    raw_commands = raw_commands.replace("-Werror", "")

    commands = json.loads(raw_commands)
    res = [x for x in commands if x["file"] == "$FILE"]
    return res


def remove_explicit_path(compile_command: str, cwd: Path) -> str:
    return compile_command.replace(str(cwd) + "/", "")


def write_compile_commands(compile_commands: Any, cwd: Path):
    new_compile_commands_path = cwd.absolute() / "compile_commands.json"
    with open(str(new_compile_commands_path), "w") as file:
        file.write(json.dumps(compile_commands))


def create_interestingness_test(args: Namespace, cwd: Path, compile_command: str):
    compile_command = remove_explicit_path(compile_command, cwd)

    with open(f"{cwd}/test.sh", "w") as file:
        file.write("#!/bin/bash\n")

        file.write(f'FILE="{cwd / args.source_file.name}"\n')

        if args.compile_error:
            if args.verifying_compiler:
                verifying_compiler_args: str
                if args.verifying_compiler_args:
                    verifying_compiler_args = args.verifying_compiler_args
                else:
                    verifying_compiler_args = compile_command[
                        compile_command.find(" ") :
                    ]
                file.write(args.verifying_compiler + f" {verifying_compiler_args} && ")
            file.write(
                "! " + compile_command + " -fno-color-diagnostics > log.txt 2>&1"
            )
        else:
            file.write(
                compile_command
                + " -Wfatal-errors -fno-color-diagnostics > log.txt 2>&1"
            )

        if args.interesting_command:
            interesting_command = args.interesting_command.replace(
                str(args.source_file), "$FILE"
            )
            interesting_command = re.sub(
                r"-p [^ ]*", f"-p {str(cwd)}", interesting_command
            )
            log.info(f"interesting_command: {interesting_command}")

            file.write(f" && {interesting_command}\n")

        chmod(file.name, stat(file.name).st_mode | S_IEXEC)


def setup_test_folder(args: Namespace, cwd: Path):
    compile_commands = get_compile_commands_entry_for_file(
        args.source_file, args.build_dir, cwd
    )
    write_compile_commands(compile_commands, cwd)
    file_path: Path = args.source_file
    copy(file_path, cwd / file_path.name)
    compile_command = compile_commands[0]["command"]
    if args.preprocess:
        preprocess_file(cwd, file_path, compile_command)

    create_interestingness_test(args, cwd, compile_command)


def preprocess_file(cwd: Path, file_path: Path, compile_command: str):
    c = (
        compile_command.replace(
            "-o output.cpp.o", f"-E -P -o {cwd / file_path.name}.tmp"
        )
        .replace("$FILE", f"{cwd / file_path.name}")
        .split(" ")
    )

    log.info("preprocess: " + " ".join(c))

    call(c)
    copy(f"{cwd / file_path.name}.tmp", f"{cwd / file_path.name}")


def load_compile_commands(dir: Path):
    compile_commands_file = dir / "compile_commands.json"
    compile_commands_raw = compile_commands_file.read_text()
    return json.loads(compile_commands_raw)


def get_cpp_std_from_compile_commands(cwd: Path):
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


def reduce_input(args: Namespace, cwd: Path):
    invocation: list[str] = [args.reduce_bin]

    if "cvise" in args.reduce_bin:
        invocation.append(f"--clang-delta-std={get_cpp_std_from_compile_commands(cwd)}")
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

    call(invocation, cwd=cwd)


def reduce_existing(args: Namespace):
    set_reduce_bin(args)

    existing_path = args.rerun_existing

    if not existing_path.exists():
        log.error(f"path of rerun_existing does not exist: {existing_path}")
        return

    if args.preprocess:
        compile_commands = load_compile_commands(existing_path)
        compile_command: str = compile_commands[0]["command"]
        file_path: Path = args.source_file
        preprocess_file(existing_path, file_path, compile_command)

    reduce_input(args, existing_path)


def reduce_new(args: Namespace):
    set_reduce_bin(args)

    args.source_file = args.source_file.resolve()
    args.build_dir = args.build_dir.resolve()

    cwd = args.build_dir / ("reducer/" + str(uuid4().hex))
    cwd.mkdir(exist_ok=True, parents=True)

    if args.interesting_command:
        args.interesting_command = args.interesting_command.replace(
            str(args.build_dir), str(cwd)
        )

    setup_test_folder(args, cwd)
    reduce_input(args, cwd)


def main():
    parser = init_argparse()
    args = parser.parse_args()

    if args.verifying_compiler_args and not args.verifying_compiler:
        log.error("option --verifying-compiler-args requires --verifying-compiler")

    log.info(f"{args}")

    if args.rerun_existing:
        reduce_existing(args)
    else:
        reduce_new(args)


if __name__ == "__main__":
    main()
