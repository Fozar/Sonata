import getopt
import os
import sys
from pathlib import Path

from babel.messages.frontend import CommandLineInterface

APP_DIR = "sonata"
LOCALE = "ru_RU"


def main(argv):
    allowable_modes = ("extract", "init", "update", "compile")
    mode = None

    def show_help():
        print(
            "make_locales.py -m <mode>\nAllowable modes: " + ", ".join(allowable_modes)
        )

    try:
        opts, args = getopt.getopt(argv, "hm:", ["help", "mode="])
    except getopt.GetoptError:
        show_help()
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-h":
            show_help()
            sys.exit()
        elif opt in ("-m", "--mode"):
            try:
                if arg not in allowable_modes:
                    raise NotImplemented
            except NotImplemented:
                show_help()
                sys.exit(2)
            else:
                mode = arg

        if mode is None:
            show_help()
            sys.exit(2)
        elif mode == "extract":
            extract_locales()
        elif mode == "init":
            init_locales()
        elif mode == "update":
            update_locales()
        elif mode == "compile":
            compile_locales()


def extract_locales():
    output_dir = "locales"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    CommandLineInterface().run(
        [
            "pybabel",
            "extract",
            APP_DIR,
            "-o",
            os.path.join(output_dir, f"{APP_DIR}.pot"),
        ]
    )


def init_locales():
    output_dir = "locales"
    input_file = os.path.join(output_dir, f"{APP_DIR}.pot")
    CommandLineInterface().run(
        ["pybabel", "init", "-i", input_file, "-d", output_dir, "-l", LOCALE]
    )


def update_locales():
    output_dir = "locales"
    input_file = os.path.join(output_dir, f"{APP_DIR}.pot")
    CommandLineInterface().run(
        ["pybabel", "update", "-i", input_file, "-d", output_dir]
    )


def compile_locales():
    input_dir = "locales"
    CommandLineInterface().run(["pybabel", "compile", "-d", input_dir, "--statistics"])


if __name__ == "__main__":
    main(sys.argv[1:])
