from pathlib import Path


def grep_file_content(pattern: str, file: Path) -> str:
    return f' && python -c \'import re; from pathlib import Path; exit(re.search("{pattern}", Path("{file}").read_text()) is None)\''
