import logging
from typing import Any, Callable, Awaitable, Dict, Optional

log = logging.getLogger(__name__)

# Axis/bool/enum callbacks
InputCallback = Callable[[Any], Awaitable[None]]

# Event callbacks (must return handled status)
EventCallback = Callable[[], Awaitable[bool]]


class InputRegistry:
    def __init__(self):
        self._inputs: Dict[str, Dict[str, Any]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._state: Dict[str, Any] = {}

    def register_input(
        self,
        name: str,
        type_: str = "axis",
        *,
        callback: Optional[Callable] = None,
        values: Optional[list] = None,
    ):
        """
        Register an input.

        type_:
            axis   -> float/int
            bool   -> boolean
            enum   -> value from list
            event  -> trigger only (no value)
        """

        self._inputs[name] = {
            "type": type_,
            "values": values,
        }

        if callback:
            self._callbacks[name] = callback

    async def handle_input(self, name: str, value: Any = None):
        if name not in self._inputs:
            log.warning("Unknown input: %s", name)
            return

        spec = self._inputs[name]
        t = spec["type"]

        # Events handled separately
        if t == "event":
            await self._handle_event(name)
            return

        if not self._validate(name, value):
            log.warning("Invalid value for input %s", name)
            return

        self._state[name] = value

        cb = self._callbacks.get(name)
        if cb:
            try:
                await cb(value)
            except Exception:
                log.exception("Input callback error: %s", name)

    async def _handle_event(self, name: str):
        cb = self._callbacks.get(name)

        if not cb:
            log.warning("Event %s has no callback", name)
            return

        try:
            handled = await cb()

            if handled is False:
                log.warning("Event %s not acknowledged by handler", name)

        except Exception:
            log.exception("Event callback error: %s", name)

    def _validate(self, name: str, value: Any) -> bool:
        spec = self._inputs[name]
        t = spec["type"]

        if t == "axis":
            return isinstance(value, (int, float))

        if t == "bool":
            return isinstance(value, bool)

        if t == "enum":
            return value in (spec.get("values") or [])

        if t == "event":
            return True

        return False

    @property
    def state(self):
        return dict(self._state)