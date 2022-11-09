# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from merino.providers import BaseProvider
from merino.providers.base import BaseSuggestion, SuggestionRequest


class CorruptProvider(BaseProvider):
    """A test corrupted provider that raises `RuntimeError` for all queries received"""

    def __init__(self) -> None:
        self._name = "corrupted"

    async def initialize(self) -> None:
        ...

    @property
    def enabled_by_default(self) -> bool:
        return True

    def hidden(self) -> bool:
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        raise RuntimeError(srequest.query)


class HiddenProvider(BaseProvider):
    def __init__(self, enabled_by_default) -> None:
        self._enabled_by_default = enabled_by_default
        self._name = "hidden"

    async def initialize(self) -> None:
        ...

    def hidden(self) -> bool:
        return True

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        raise RuntimeError(srequest.query)


class NonsponsoredSuggestion(BaseSuggestion):
    """Model for nonsponsored suggestions."""

    block_id: int
    full_keyword: str
    advertiser: str


class NonsponsoredProvider(BaseProvider):
    """A test nonsponsored provider that only responds to query 'nonsponsored'"""

    def __init__(self, enabled_by_default) -> None:
        self._enabled_by_default = enabled_by_default
        self._name = "non-sponsored"

    async def initialize(self) -> None:
        ...

    def hidden(self) -> bool:
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        if srequest.query.lower() == "nonsponsored":
            return [
                NonsponsoredSuggestion(
                    block_id=0,
                    full_keyword="nonsponsored",
                    title="nonsponsored title",
                    url="https://www.nonsponsored.com",
                    provider="test provider",
                    advertiser="test nonadvertiser",
                    is_sponsored=False,
                    icon="https://www.nonsponsoredicon.com",
                    score=0.5,
                )
            ]
        else:
            return []


class SponsoredSuggestion(BaseSuggestion):
    """Model for sponsored suggestions."""

    block_id: int
    full_keyword: str
    advertiser: str
    impression_url: str
    click_url: str


class SponsoredProvider(BaseProvider):
    """A test sponsored provider that only responds to query 'sponsored'"""

    def __init__(self, enabled_by_default) -> None:
        self._enabled_by_default = enabled_by_default
        self._name = "sponsored"

    async def initialize(self) -> None:
        ...

    def hidden(self) -> bool:
        return False

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        if srequest.query.lower() == "sponsored":
            return [
                SponsoredSuggestion(
                    block_id=0,
                    full_keyword="sponsored",
                    title="sponsored title",
                    url="https://www.sponsored.com",
                    impression_url="https://www.sponsoredimpression.com",
                    click_url="https://www.sponsoredclick.com",
                    provider="test provider",
                    advertiser="test advertiser",
                    is_sponsored=True,
                    icon="https://www.sponsoredicon.com",
                    score=0.5,
                )
            ]
        else:
            return []
