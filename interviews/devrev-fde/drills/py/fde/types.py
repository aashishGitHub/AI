from collections.abc import Callable

type Clock = Callable[[], float]
type Json = None | bool | int | float | str | list[Json] | dict[str, Json]
