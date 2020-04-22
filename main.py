import getopt
import sys

from sonata import create_app


def main(argv: list):
    debug = False

    def show_help():
        print("-D or --DEBUG to debug")

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
            debug = True

    create_app(debug)


if __name__ == "__main__":
    main(sys.argv[1:])
