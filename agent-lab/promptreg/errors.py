from __future__ import annotations


class PromptRegError(Exception):
    pass


class UnknownPrompt(PromptRegError):
    pass


class VersionExists(PromptRegError):
    pass


class TamperError(PromptRegError):
    pass


class InvalidReport(PromptRegError):
    pass


class StateError(PromptRegError):
    pass
