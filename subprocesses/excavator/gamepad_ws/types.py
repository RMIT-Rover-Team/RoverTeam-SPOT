from typing import TypedDict, Literal

class AxisData(TypedDict):
    id: int
    value: float

class ButtonData(TypedDict):
    id: int
    pressed: bool

class GamepadMessage(TypedDict):
    type: Literal["axis", "button"]
    data: AxisData | ButtonData