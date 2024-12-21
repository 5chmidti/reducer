from argparse import Namespace
from pathlib import Path
from shutil import copy

from reducer.lib.setup import (
    create_interestingness_test,
    get_compile_commands_entry_for_file,
    preprocess_file,
    write_compile_commands,
)


class Driver:
    def __init__(self) -> None:
        pass

    def setup(self, args: Namespace, cwd: Path) -> None:
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

    def create_interestingness_test(
        self,
        args: Namespace,
        cwd: Path,
        compile_command_json: dict[str, str],
    ) -> None:
        pass
