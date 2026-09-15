"""Rendered model messages with their trusted, pre-rendering context structure.

Consumers must not infer metadata by parsing user-authored strings.
"""


class ContextMessages(list):
    def __init__(self, messages, sections):
        super().__init__(messages)
        self.sections = sections
