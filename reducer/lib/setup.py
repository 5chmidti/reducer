import json
import re
from argparse import Namespace
from os import cpu_count
from pathlib import Path
from shutil import copy, copyfile
from stat import S_IEXEC
from subprocess import call, run
from typing import Any

from reducer.lib.log import log
from reducer.lib.prompt import prompt_yes_no


def setup_test_folder(args: Namespace, cwd: Path) -> None:
    compile_commands = get_compile_commands_entry_for_file(
        args.file,
        args.build_dir,
    )
    write_compile_commands(compile_commands, cwd)
    file_path: Path = args.file
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


def replace_path_in_list(
    strings: list[str],
    file: Path,
    new_path_str: str,
) -> list[str]:
    return [
        string.replace(str(file), new_path_str)
        .replace(str(file.absolute()), new_path_str)
        .replace(str(file.resolve()), new_path_str)
        for string in strings
    ]


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


def get_compile_command(compile_command: str, cwd: Path) -> str:
    return str(
        remove_explicit_path(compile_command, cwd)
        .replace("-fcolor-diagnostics", "")
        .replace("-Wdocumentation", "")
        .replace("-fopenmp=libomp", "-fopenmp")
        + " -Wfatal-errors -fno-color-diagnostics > log.txt 2>&1",
    )


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
        + get_compile_command(compile_command, cwd)
        + " -Wfatal-errors -fno-color-diagnostics > log.txt 2>&1",
    )

    if args.interesting_command:
        args.interesting_command = replace_path(
            args.interesting_command,
            args.build_dir,
            str(cwd),
        )
        interesting_command = replace_path(
            args.interesting_command,
            args.file,
            args.file.name,
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


def reduce(args: Namespace, cwd: Path) -> None:
    invocation: list[str] = [args.reduce_bin]

    if "cvise" in args.reduce_bin:
        invocation.append(
            f"--clang-delta-std={get_csvise_supported_cpp_std(args, get_cpp_std_from_compile_commands(cwd))}",
        )
        invocation.append("--to-utf8")

    invocation.append(f"--n={args.jobs if args.jobs else cpu_count()}")

    if args.timeout:
        invocation.append(f"--timeout={args.timeout}")

    invocation.append("test.sh")
    invocation.append(args.file.name)

    log.info(invocation)

    compile_commands = get_compile_commands_entry_for_file(
        args.file,
        cwd,
    )
    compile_command = compile_commands[0]["command"]
    iteration = 0
    while True:
        preprocess_file(cwd, cwd / args.file.name, compile_command)
        return_code = call(invocation, cwd=cwd)
        if return_code != 0:
            raise RuntimeError("reduction invokation failed")
        if not args.prompt_rerun or not prompt_yes_no("Continue reduction?"):
            break

        copyfile(cwd / args.file.name, cwd / (args.file.name + str(iteration)))
        iteration = iteration + 1