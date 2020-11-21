import getopt
import logging
import sys

import sentry_sdk
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from sonata import create_app


def main(argv: list):
    sentry_sdk.init(
        "https://107f8ff27a7a4f5fb08cca733aaaa35f@o439403.ingest.sentry.io/5406178",
        traces_sample_rate=1.0,
        integrations=[
            AioHttpIntegration(),
            LoggingIntegration(
                level=logging.INFO,  # Capture info and above as breadcrumbs
                event_level=logging.ERROR,  # Send errors as events
            ),
        ],
    )
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
