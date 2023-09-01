from argparse import ArgumentParser, Namespace, BooleanOptionalAction
import json
from os import chmod, stat
import re
from shutil import copy
from stat import S_IEXEC
from subprocess import call
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
        default="cvise",
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
        action=BooleanOptionalAction
    )
    parser.add_argument(
        "--preprocess",
        help="run preprocessor on source file",
        action=BooleanOptionalAction,
        default=True,
        required=False,
        type=bool,
    )
    parser.add_argument(
        "--rerun-existing",
        help="run a reduction on an existing reducer folder",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--jobs",
        help="number of jobs to run with the reducer",
        required=False,
        type=int,
    )
    return parser


def get_compile_commands_for_file(args: Namespace, cwd: Path):
    file_path: Path = args.source_file
    build_dir = args.build_dir

    compile_commands_file = build_dir / "compile_commands.json"
    new_file_path = cwd.absolute() / str(file_path.name)
    log.info(str(new_file_path))
    raw_commands = compile_commands_file.read_text()
    raw_commands = raw_commands.replace(str(file_path), str(new_file_path))
    raw_commands = re.sub(r"-o .*\.o", "-o output.cpp.o", raw_commands)
    raw_commands = raw_commands.replace("-c ", f"-I{file_path.parent} -c ")
    raw_commands = raw_commands.replace(
        "-c ", "-Wfatal-errors -Wno-invalid-constexpr -w -c "
    )
    raw_commands = raw_commands.replace("-Werror", "")

    commands = json.loads(raw_commands)
    res = next(x for x in commands if x["file"] == str(new_file_path))
    log.info(res)
    return [res]


def remove_explicit_path(compile_command:str, cwd: Path) ->str:
    return compile_command.replace(str(cwd)+"/","")


def write_compile_commands(compile_commands: Any, cwd: Path):
    new_compile_commands_path = cwd.absolute() / "compile_commands.json"
    with open(str(new_compile_commands_path), "w") as file:
        file.write(json.dumps(compile_commands))


def create_interestingness_test(args: Namespace, cwd: Path, compile_command: str):
    compile_command = remove_explicit_path(compile_command, cwd)

    with open(f"{cwd}/test.sh", "w") as file:
        if args.compile_error:
            file.write("#!/bin/bash\n")
            file.write(
                "! "
                +
                compile_command
                + ' -fno-color-diagnostics > log.txt 2>&1 && grep ": fatal error: ambiguous partial specializations of \'formatter<boost::container::flat_set<int>>\'" log.txt && grep "1 error generated" log.txt'
            )
            chmod(file.name, stat(file.name).st_mode | S_IEXEC)
            return

        file.write("#!/bin/bash\n")

        compile_command = compile_command + " -Wfatal-errors "
        file.write(compile_command + " && ")

        interesting_command =  args.interesting_command.replace(str(args.source_file),str(args.source_file.name))
        interesting_command = re.sub(r"-p [^ ]*", f"-p {str(cwd)}", interesting_command)
        file.write(
            f"{interesting_command}\n"
        )
        chmod(file.name, stat(file.name).st_mode | S_IEXEC)


def setup_test_folder(args: Namespace, cwd: Path):
    compile_commands = get_compile_commands_for_file(args, cwd)
    write_compile_commands(compile_commands, cwd)
    file_path: Path = args.source_file
    copy(file_path, cwd / file_path.name)
    if args.preprocess:
        c = (
            compile_commands[0]["command"]
            .replace("-o output.cpp.o", f"-E -P -o {cwd / file_path.name}.tmp")
            .split(" ")
        )

        log.info(c)

        call(c)
        copy(f"{cwd / file_path.name}.tmp", f"{cwd / file_path.name}")

    create_interestingness_test(args, cwd, compile_commands[0]["command"])


def reduce_input(args: Namespace, cwd: Path):
    invocation: list[str] = [
        args.reduce_bin,
        "test.sh",
        args.source_file.name,
    ]

    if args.jobs:
        invocation.append(f"--n={args.jobs}")
    else:
        invocation.append(f"--n={cpu_count()}")


    log.info(invocation)

    if not args.rerun_existing:
        setup_test_folder(args, cwd)
    call(invocation, cwd=cwd)


def main():
    parser = init_argparse()
    args = parser.parse_args()
    log.info(f"{args}")

    if  args.rerun_existing:
        existing_path = Path(args.rerun_existing)
        if not existing_path.exists():
            log.error(f"path of rerun_existing does not exist: {existing_path}")
        cwd = existing_path
        reduce_input(args, cwd)
    else:
        real_source_file = args.source_file.resolve()
        real_build_dir = args.build_dir.resolve()

        build_dir: Path = real_build_dir

        cwd = build_dir / ("reducer/" + str(uuid4().hex))
        cwd.mkdir(exist_ok=True, parents=True)

        args.interesting_command = args.interesting_command.replace(
            str(Path(args.source_file).absolute()),
            str(real_source_file.name),
        )

        args.interesting_command = args.interesting_command.replace(
            str(Path(args.build_dir).absolute()), str(cwd)
        )

        args.source_file = real_source_file
        args.build_dir = real_build_dir

        reduce_input(args, cwd)


if __name__ == "__main__":
    main()
