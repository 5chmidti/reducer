from argparse import Namespace
from pathlib import Path
from shutil import copy

from reducer.lib.setup import (
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

    def create_interestingness_test(
        self,
        args: Namespace,
        cwd: Path,
        compile_command_json: dict[str, str],
    ) -> None:
        pass
