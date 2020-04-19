import getopt
import sys

from sonata import create_app
from sonata.config import settings


def main(argv: list):
    def show_help():
        print(
            "-D or --DEBUG to debug"
        )

    try:
        opts, args = getopt.getopt(argv, "hD", ["help", "DEBUG"])
    except getopt.GetoptError:
        show_help()
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-h":
            show_help()
            sys.exit()
        elif opt in ("-D", "--DEBUG"):
            settings.DEBUG = True

    create_app()


if __name__ == "__main__":
    main(sys.argv[1:])
