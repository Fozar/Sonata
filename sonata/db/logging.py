import logging
import os
from datetime import datetime
from logging import handlers

from pymongo import monitoring


class CommandLogger(monitoring.CommandListener):
    def __init__(self, logger):
        self.logger = logger

    def started(self, event):
        self.logger.debug(
            "Command {0.command_name} with request id "
            "{0.request_id} started on server "
            "{0.connection_id}".format(event)
        )

    def succeeded(self, event):
        self.logger.debug(
            "Command {0.command_name} with request id "
            "{0.request_id} on server {0.connection_id} "
            "succeeded in {0.duration_micros} "
            "microseconds".format(event)
        )

    def failed(self, event):
        self.logger.error(
            "Command {0.command_name} with request id "
            "{0.request_id} on server {0.connection_id} "
            "failed in {0.duration_micros} "
            "microseconds".format(event)
        )


class HeartbeatLogger(monitoring.ServerHeartbeatListener):
    def __init__(self, logger):
        self.logger = logger

    def started(self, event):
        self.logger.debug("Heartbeat sent to server " "{0.connection_id}".format(event))

    def succeeded(self, event):
        # The reply.document attribute was added in PyMongo 3.4.
        self.logger.debug(
            "Heartbeat to server {0.connection_id} "
            "succeeded with reply "
            "{0.reply.document}".format(event)
        )

    def failed(self, event):
        self.logger.error(
            "Heartbeat to server {0.connection_id} "
            "failed with error {0.reply}".format(event)
        )


def setup_logger():
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] - %(filename)s - %(message)s")
    )
    stream_handler.setLevel(logging.INFO)
    file_handler = handlers.TimedRotatingFileHandler(
        filename=f"{os.getcwd()}/logs/mongo/{datetime.utcnow().date()}.log",
        when="midnight",
        backupCount=3,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] - %(filename)s - %(message)s")
    )
    file_handler.setLevel(logging.DEBUG)
    logger = logging.Logger("mongo", level=logging.DEBUG)
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)
    monitoring.register(CommandLogger(logger))
    monitoring.register(HeartbeatLogger(logger))
    return logger
