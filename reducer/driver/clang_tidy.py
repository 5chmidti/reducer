from argparse import ArgumentParser, Namespace
from pathlib import Path
from re import findall, match, sub
from stat import S_IEXEC
from subprocess import call, run
from typing import Optional

from reducer.lib.driver import Driver
from reducer.lib.log import log
from reducer.lib.setup import (
    get_compile_command,
    remove_explicit_path,
    replace_path_in_list,
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

        call(
            [
                *clang_tidy_invocation,
                f"--config-file={tidy_config}",
                "--dump-config",
                ">",
                f"{reduction_cwd}/.clang-tidy",
            ],
        )
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

    # Cleanup paths in invocation
    res = replace_path_in_list(
        res,
        args.build_dir,
        str(cwd),
    )
    res = replace_path_in_list(
        res,
        args.file,
        args.file.name,
    )
    return [
        sub(
            r"-p[ =]?[^ ]*",
            f"-p {cwd!s}",
            string,
        )
        for string in res
    ]


def deduce_crashing_check_from_crash(
    clang_tidy_invocation: list[str],
    reduction_cwd: Path,
) -> Optional[str]:
    res = run(
        clang_tidy_invocation,
        cwd=reduction_cwd,
        check=False,
        capture_output=True,
    )
    stderr = res.stderr.decode()
    m = match("ASTMatcher: Processing '([^']*)'", stderr)
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


def reduce_clang_tidy_crash(args: Namespace, reduction_cwd: Path) -> None:
    clang_tidy_invocation = build_clang_tidy_invocation(args, reduction_cwd)
    write_existing_clang_tidy_config(
        clang_tidy_invocation,
        args.build_dir,
        reduction_cwd,
    )
    crashing_checks = deduce_crashing_check(clang_tidy_invocation, reduction_cwd)
    if len(crashing_checks) == 0:
        log.error("Failed to deduce the check that crashes clang-tidy")
    log.info(f"Deduced that the check that crashes clang-tidy is {crashing_checks}")


class ClangTidyDriver(Driver):
    def __init__(self) -> None:
        pass

    def add_arguments(self, common_parser: ArgumentParser, sub_parser) -> None:
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

    def setup(self, args: Namespace, cwd: Path) -> None:
        super().setup(args, cwd)

    def create_interestingness_test(
        self,
        args: Namespace,
        cwd: Path,
        compile_command_json: dict[str, str],
    ) -> None:
        compile_command = remove_explicit_path(compile_command_json["command"], cwd)

        file = Path(f"{cwd}/test.sh")
        file_content: str = "#!/bin/bash\n"

        if args.timeout:
            file_content = file_content + f"! timeout {args.timeout} "
        file_content = str(
            file_content
            + get_compile_command(compile_command, cwd)
            + " -Wfatal-errors -fno-color-diagnostics > log.txt 2>&1",
        )

        clang_tidy_invocation = build_clang_tidy_invocation(args, cwd)
        write_existing_clang_tidy_config(
            clang_tidy_invocation,
            args.build_dir,
            cwd,
        )
        crashing_checks = deduce_crashing_check(clang_tidy_invocation, cwd)
        clang_tidy_invocation.append(f"--checks=-*,{','.join(crashing_checks)}")

        file_content = file_content + " &&"
        if args.timeout:
            file_content = file_content + f" ! timeout {args.timeout}"
        file_content = str(
            file_content + f" {' '.join(clang_tidy_invocation)}\n",
        )

        file.write_text(file_content)
        file.chmod(file.stat().st_mode | S_IEXEC)
