from os import environ
from pathlib import Path
from shutil import rmtree
from subprocess import call
from unittest import TestCase, main

from reducer import reducer


class TestReducer(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_dir = Path(__file__).parent / "project"
        cls.build_dir = cls.project_dir / "build"
        if cls.build_dir.exists():
            rmtree(cls.build_dir)
        cls.build_dir.mkdir()
        env = environ
        env["CC"] = "clang"
        env["CXX"] = "clang++"
        build_project = f"cmake -S {cls.project_dir} -B {cls.build_dir}"
        reducer.log.info(build_project)
        call(build_project.split(" "), env=env)

    def do_reduction(self, invocation: list[str]) -> None:
        parser = reducer.init_common_argparse()
        args = parser.parse_args(invocation)
        reducer.log.info(f"{args}")

        if args.rerun_existing:
            reducer.reduce_existing(args)
        else:
            reducer.reduce_new(args)

    def test_clang_tidy_contains(self) -> None:
        self.do_reduction(
            [
                f"{self.project_dir}/src/main.cpp",
                "--build-dir",
                f"{self.build_dir}",
                "--interesting-command",
                f"clang-tidy -p {self.build_dir} --checks=\"-*,readability-const-return-type\" main.cpp 2>&1 | grep 'readability-const-return-type'",
            ],
        )

    def test_clang_div_by_zero(self) -> None:
        self.do_reduction(
            [
                f"{self.project_dir}/src/main.cpp",
                "--build-dir",
                f"{self.build_dir}",
                "--interesting-command",
                "grep -- '-Wdivision-by-zero' log.txt",
            ],
        )


if __name__ == "__main__":
    main()
