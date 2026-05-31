"""Programmatic client for the Plenipo relay."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlenipoClientOptions:
    """Configuration for :class:`PlenipoClient`."""

    did_private_key: str
    relay_url: str


class PlenipoClient:
    """Programmatic client for the Plenipo relay (scaffold)."""

    def __init__(self, options: PlenipoClientOptions) -> None:
        self._did_private_key = options.did_private_key
        self._relay_url = options.relay_url

    @property
    def relay_url(self) -> str:
        return self._relay_url
