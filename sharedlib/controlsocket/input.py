# sharedlib/controlsocket/input.py
import logging
from typing import Any, Callable, Awaitable, Dict, Optional

log = logging.getLogger(__name__)
InputCallback = Callable[[Any], Awaitable[None]]


class InputRegistry:
    def __init__(self):
        self._inputs: Dict[str, Dict[str, Any]] = {}
        self._callbacks: Dict[str, InputCallback] = {}
        self._state: Dict[str, Any] = {}

    def register_input(
        self,
        name: str,
        type_: str = "axis",
        *,
        callback: Optional[InputCallback] = None,
        values: Optional[list] = None,  # for enums
    ):
        self._inputs[name] = {
            "type": type_,
            "values": values,
        }
        if callback:
            self._callbacks[name] = callback

    async def handle_input(self, name: str, value: Any):
        if name not in self._inputs:
            log.warning("Unknown input: %s", name)
            return

        if not self._validate(name, value):
            log.warning("Invalid value for input %s", name)
            return

        self._state[name] = value

        if name in self._callbacks:
            try:
                await self._callbacks[name](value)
            except Exception as e:
                log.exception("Input callback error: %s", e)

    def _validate(self, name: str, value: Any) -> bool:
        spec = self._inputs[name]
        t = spec["type"]

        if t == "axis":
            if not isinstance(value, (int, float)):
                return False

            return True

        if t == "bool":
            return isinstance(value, bool)

        if t == "enum":
            return value in (spec.get("values") or [])

        return True

    @property
    def state(self):
        return dict(self._state)