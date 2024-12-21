from lib.log import log


def prompt_yes_no(question: str, assume_yes: bool = True) -> bool:
    log.info(f"{question} [{"Y" if assume_yes else "y" }/{"n" if assume_yes else "N"}")
    decision = input().lower()
    match decision:
        case "y":
            return True
        case "yes":
            return True
        case "n":
            return False
        case "no":
            return False
        case "":
            return assume_yes
    return False
