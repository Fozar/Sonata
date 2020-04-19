from discord.ext import commands


class NoPremium(commands.CheckFailure):
    """Exception raised when an operation does not work on the guild without premium.

    This inherits from :exc:`CheckFailure`
    """

    def __init__(self, message=None):
        super().__init__(message or "This command cannot be used without premium.")
