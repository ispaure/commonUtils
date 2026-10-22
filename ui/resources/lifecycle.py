"""Captured resource identity and cooperative ownership of window operations."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceIdentity:
    provider: object
    generation: int


class ResourceOperations:
    """Retain every worker/window owner until it is idle, including during close."""
    def __init__(self):
        self.closing = False
        self.generation = 0
        self.provider = None
        self._owners = {}

    def bind(self, provider):
        if self.busy:
            raise RuntimeError('Wait for resource operations before changing provider.')
        self.provider = provider
        self.generation += 1
        return self.capture()

    def capture(self):
        return ResourceIdentity(self.provider, self.generation)

    def accepts(self, identity):
        return not self.closing and identity.provider is self.provider and identity.generation == self.generation

    def own(self, owner, *, busy=None, cancel=None):
        self._owners[id(owner)] = (owner, busy or (lambda: owner.busy), cancel or owner.request_cancel)
        return owner

    def retire(self, owner):
        record = self._owners.get(id(owner))
        if record is not None and record[1]():
            raise RuntimeError('A busy resource owner cannot be retired.')
        self._owners.pop(id(owner), None)

    @property
    def busy(self):
        return any(busy() for _, busy, _ in tuple(self._owners.values()))

    def stop(self):
        self.closing = True
        for _, _, cancel in tuple(self._owners.values()):
            cancel()
        return self.busy

    def resume(self):
        if self.busy:
            raise RuntimeError('Wait for resource workers before resuming.')
        self.closing = False


def operations_for(owner):
    lifecycle = getattr(owner, '_resource_operations', None)
    if lifecycle is None:
        lifecycle = owner._resource_operations = ResourceOperations()
    return lifecycle
