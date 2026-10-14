"""Toolkit-independent destination and route state supplied by the host."""


class NavigationState:
    def __init__(self, destinations, *, destination=None):
        self.destinations = tuple(destinations)
        if not self.destinations or any(not isinstance(key, str) or not key for key in self.destinations):
            raise ValueError('Destinations require nonempty string identities.')
        if len(set(self.destinations)) != len(self.destinations):
            raise ValueError('Destination identities must be unique.')
        self.routes = {key: [] for key in self.destinations}
        self.select(destination or self.destinations[0])

    def select(self, destination):
        if destination not in self.destinations:
            raise ValueError('Unknown navigation destination.')
        self.destination = destination

    def push(self, route):
        if not isinstance(route, str) or not route or len(route) > 200:
            raise ValueError('Invalid navigation route.')
        self.routes[self.destination].append(route)

    def back(self):
        routes = self.routes[self.destination]
        return routes.pop() if routes else None
