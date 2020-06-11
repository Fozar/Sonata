from aiohttp_security import AbstractAuthorizationPolicy


class DBAuthorizationPolicy(AbstractAuthorizationPolicy):
    def __init__(self, db):
        self.db = db

    async def authorized_userid(self, identity: str):
        cursor = self.db.users.find({"id": int(identity)}, {"id": True})
        return identity if await cursor.fetch_next else None

    async def permits(self, identity, permission, context=None):
        """
        context : int
            guild id
        """
        if identity is None:
            return False
        elif identity == "149722383165423616":
            return True

        cursor = self.db.users.find({"id": int(identity)}, {"id": True})
        if not await cursor.fetch_next:
            return False

        if context:
            cursor = self.db.guilds.find(
                {"id": context, "owner_id": int(identity)}, {"premium": True},
            )
            if not await cursor.fetch_next:
                return False

            guild_conf = cursor.next_object()

            if permission == "premium" and not guild_conf["premium"]:
                return False

        return True
