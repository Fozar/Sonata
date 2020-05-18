from discord.ext import commands


class NoPremium(commands.CheckFailure):
    """Exception raised when an operation does not work on the guild without premium.

    This inherits from :exc:`CheckFailure`
    """

    def __init__(self, message=None):
        super().__init__(message or "This command cannot be used without premium.")


class SubscriptionNotFound(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return self.message
        else:
            return "Twitch subscription not found"
