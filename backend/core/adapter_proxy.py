from typing import Generic, TypeVar

AdapterT = TypeVar("AdapterT")


class AdapterProxy(Generic[AdapterT]):
    """Keeps a stable reference while allowing the adapter to be replaced."""

    def __init__(self, adapter: AdapterT):
        self._adapter = adapter

    @property
    def adapter(self) -> AdapterT:
        return self._adapter

    def set_adapter(self, adapter: AdapterT) -> None:
        self._adapter = adapter

    def __getattr__(self, name):
        return getattr(self._adapter, name)
