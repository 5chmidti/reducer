from argparse import ArgumentParser, Namespace
from pathlib import Path
from stat import S_IEXEC, S_IROTH, S_IXGRP, S_IXOTH

from reducer.lib.driver import Driver
from reducer.lib.grep import grep_file_content
from reducer.lib.setup import (
    get_compile_command,
)


class CompilerCrashDriver(Driver):
    def __init__(self) -> None:
        pass

    def add_arguments(self, common_parser: ArgumentParser, sub_parser) -> None:
        parser = sub_parser.add_parser(
            name="compiler-crash",
            help="Reduce a compiler crash",
            parents=[common_parser],
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

    def setup(self, args: Namespace, cwd: Path) -> None:
        super().setup(args, cwd)

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

        verifying_compiler_args: str
        if args.verifying_compiler_args:
            verifying_compiler_args = args.verifying_compiler_args
        else:
            verifying_compiler_args = compile_command[compile_command.find(" ") :]
        file_content = str(
            file_content
            + str(args.verifying_compiler)
            + f" {verifying_compiler_args} && ",
        )

        if args.timeout:
            file_content = file_content + f"! timeout {args.timeout} "
        file_content = str(
            file_content
            + get_compile_command(compile_command, cwd)
            + " -Wfatal-errors -fno-color-diagnostics > log.txt 2>&1",
        )

        if args.grep:
            file_content = file_content + grep_file_content(args.grep, cwd / "log.txt")
        if args.grep_file:
            file_content = file_content + grep_file_content(
                args.grep_file,
                cwd / args.file.name,
            )

        file.write_text(file_content)
        file.chmod(file.stat().st_mode | S_IEXEC | S_IXOTH | S_IROTH | S_IXGRP)
