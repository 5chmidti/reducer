import sys
from argparse import ArgumentParser, Namespace
from json import loads
from pathlib import Path
from re import findall, match, search
from stat import S_IEXEC, S_IROTH, S_IXGRP, S_IXOTH
from subprocess import run
from typing import Optional

from reducer.lib.driver import Driver
from reducer.lib.grep import grep_file_content
from reducer.lib.log import log
from reducer.lib.setup import (
    get_compile_command,
)


def write_existing_clang_tidy_config(
    clang_tidy_invocation: list[str],
    build_dir: Path,
    reduction_cwd: Path,
) -> None:
    for p in build_dir.parents:
        tidy_config = p / ".clang-tidy"
        if not tidy_config.exists():
            continue

        res = run(
            [
                *clang_tidy_invocation,
                f"--config-file={tidy_config}",
                "--dump-config",
                ">",
                f"{reduction_cwd}/.clang-tidy",
            ],
            check=False,
        )
        (reduction_cwd / ".clang-tidy").write_bytes(res.stdout)
        return


def get_list_of_enabled_checks(
    clang_tidy_invocation: list[str],
    reduction_cwd: Path,
) -> list[str]:
    return findall(
        r"(\w+(?:-\w+)+(?:\..*)?)",
        run(
            [
                *clang_tidy_invocation,
                "--list-checks",
            ],
            cwd=reduction_cwd,
            check=False,
            capture_output=True,
        ).stdout.decode(),
    )


def build_clang_tidy_invocation(args: Namespace, cwd: Path) -> list[str]:
    if args.clang_tidy_invocation:
        return args.clang_tidy_invocation
    res = [
        args.clang_tidy_binary,
        "-p",
        str(cwd),
    ]
    if args.clang_tidy_check:
        res.append(f"--checks=-*,{args.clang_tidy_check}")
    res.append(args.file.name)
    return res


def deduce_crashing_check_from_crash(
    clang_tidy_invocation: list[str],
    reduction_cwd: Path,
) -> str | None:
    res = run(
        clang_tidy_invocation,
        cwd=reduction_cwd,
        check=False,
        capture_output=True,
    )
    m = match("ASTMatcher: Processing '([^']*)'", res.stderr.decode())
    if m:
        return m.group()
    return None


def deduce_crashing_check_from_binary_search(
    clang_tidy_invocation: list[str],
    reduction_cwd: Path,
    list_of_checks: list[str],
) -> list[str]:
    if len(list_of_checks) <= 1:
        return list_of_checks

    res = run(
        [*clang_tidy_invocation, f"--checks=-*,{','.join(list_of_checks)}"],
        check=False,
        cwd=reduction_cwd,
    )
    if res.returncode == 0:
        return []

    return deduce_crashing_check_from_binary_search(
        clang_tidy_invocation,
        reduction_cwd,
        list_of_checks[: int(len(list_of_checks) / 2)],
    ) + deduce_crashing_check_from_binary_search(
        clang_tidy_invocation,
        reduction_cwd,
        list_of_checks[int(len(list_of_checks) / 2) :],
    )


def deduce_crashing_check(
    clang_tidy_invocation: list[str],
    reduction_cwd: Path,
) -> list[str]:
    deduced_from_crash = deduce_crashing_check_from_crash(
        clang_tidy_invocation,
        reduction_cwd,
    )
    if deduced_from_crash:
        return [deduced_from_crash]

    return deduce_crashing_check_from_binary_search(
        clang_tidy_invocation,
        reduction_cwd,
        get_list_of_enabled_checks(clang_tidy_invocation, reduction_cwd),
    )


def get_build_dir(args: Namespace) -> Path:
    if args.build_dir:
        return args.build_dir

    if args.clang_tidy_invocation is None:
        log.error(
            "No '--build-dir' flag or '--clang-tidy-invocation' flag was passed",
        )
        sys.exit(1)

    path = search(r"-p[\s=]([^\s])*", args.clang_tidy_invocation)
    path_str: str | None = path.group(1) if path is not None else None
    if path_str is None:
        log.error(
            "No '--build-dir' flag was passed, and the build dir could not be"
            " deduced from the '--clang-tidy-invocation' flag",
        )
        sys.exit(1)

    return Path(path_str)


class ClangTidyDriver(Driver):
    def __init__(self, args: Namespace, cwd: Path) -> None:
        super().__init__(args, cwd)
        self.create_interestingness_test(
            args,
            cwd,
            loads((cwd / "compile_commands.json").read_text())[0],
        )

    @staticmethod
    def add_arguments(common_parser: ArgumentParser, sub_parser) -> None:
        parser = sub_parser.add_parser(
            name="tidy",
            help="Reduce a clang-tidy invocation",
            parents=[common_parser],
        )
        parser.add_argument(
            "--clang-tidy-binary",
            help="The clang-tidy binary",
            type=str,
            required=False,
            default="clang-tidy",
        )
        parser.add_argument(
            "--clang-tidy-invocation",
            help="The full clang-tidy invocation to use",
            type=str,
            required=False,
        )
        parser.add_argument(
            "--clang-tidy-check",
            help="The clang-tidy check that is causing the problem",
            type=str,
            required=False,
        )
        parser.add_argument(
            "--require-post-compile",
            help="Require the applied fixes to compile",
            required=False,
            action=BooleanOptionalAction,
        )

    def create_interestingness_test(
        self,
        args: Namespace,
        cwd: Path,
        compile_command_json: dict[str, str],
    ) -> None:
        compile_command = get_compile_command(compile_command_json["command"], cwd)

        file = Path(f"{cwd}/test.sh")
        file_content: str = "#!/bin/sh\n"

        if args.timeout:
            file_content = file_content + f"! timeout {args.timeout} "
        file_content = file_content + compile_command

        clang_tidy_invocation = build_clang_tidy_invocation(args, cwd)
        log.info(f"clang-tidy invocation: '{' '.join(clang_tidy_invocation)}'")
        write_existing_clang_tidy_config(
            clang_tidy_invocation,
            get_build_dir(args),
            cwd,
        )

        file_content = file_content + " &&"
        if args.timeout:
            file_content = file_content + f" ! timeout {args.timeout}"
        if args.crash:
            crashing_checks = deduce_crashing_check(clang_tidy_invocation, cwd)
            if len(crashing_checks) != 0:
                clang_tidy_invocation.append(f"--checks=-*,{','.join(crashing_checks)}")
                log.info(
                    f"Deduced that the check that crashes clang-tidy is {crashing_checks}",
                )
            file_content = file_content + " !"
        file_content = str(
            file_content
            + " && ".join(
                f" {' '.join(clang_tidy_invocation)} > log.txt 2>&1 "
                for _ in range(args.repeat)
            ),
        )
        if args.grep:
            file_content = file_content + grep_file_content(args.grep, cwd / "log.txt")
        if args.grep_file:
            file_content = file_content + grep_file_content(
                args.grep_file,
                cwd / args.file.name,
            )

        if args.require_post_compile:
            file_content = (
                file_content + " && " + compile_command + " > post_compile_log.txt 2>&1"
            )

        log.info(f"interestingness test: '{file_content}'")
        file.write_text(file_content)
        file.chmod(file.stat().st_mode | S_IEXEC | S_IXOTH | S_IROTH | S_IXGRP)
