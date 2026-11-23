"""Actor identity resolution for task lifecycle attribution.

Resolves the actor performing task operations. Documented as attribution,
not authentication: no user accounts, passwords, or authorization
infrastructure is introduced in M4.

Resolution order:
    1. FACTORY_LAB_ACTOR environment variable
    2. getpass.getuser() fallback

Whitespace is trimmed; empty or whitespace-only values are rejected.
ActorResolutionError is raised only when neither source yields a valid
non-empty actor. The resolver callable is injectable for testing and
future multi-user/cloud identity integration.
"""

from __future__ import annotations

import getpass
import os
from typing import Callable, Optional

from factory.errors import ActorResolutionError

FACTORY_LAB_ACTOR_ENV = "FACTORY_LAB_ACTOR"


class ActorResolver:
    """Resolves the current actor identity.

    Attributes:
        resolver: Injectable callable returning an optional actor string.
    """

    def __init__(
        self, resolver: Optional[Callable[[], Optional[str]]] = None
    ) -> None:
        self._resolver = resolver or self._default_resolver

    def resolve(self) -> str:
        """Resolve and return the current actor identity.

        Returns:
            Trimmed, non-empty actor string.

        Raises:
            ActorResolutionError: If no valid actor can be resolved.
        """
        actor = self._resolver()
        if actor is None or not actor.strip():
            raise ActorResolutionError(
                "Could not resolve actor identity",
                detail=(
                    "Set the FACTORY_LAB_ACTOR environment variable or "
                    "ensure getpass.getuser() returns a valid user"
                ),
            )
        return actor.strip()

    @staticmethod
    def _default_resolver() -> Optional[str]:
        actor = os.environ.get(FACTORY_LAB_ACTOR_ENV)
        if actor is not None and actor.strip():
            return actor
        return getpass.getuser()
