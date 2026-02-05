import json
import inspect
import logging
from typing import Callable, Any

log = logging.getLogger(__name__)


class Receiver:
    """
    Decodes JSON messages and forwards them to an injected handler.
    The handler may be sync or async.
    """

    def __init__(self, handler: Callable[[dict], Any]):
        self._handler = handler

    async def receive(self, message: str):
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            log.warning("Dropped invalid JSON message: %r", message)
            return

        try:
            result = self._handler(payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            log.exception("Unhandled exception in receiver handler")