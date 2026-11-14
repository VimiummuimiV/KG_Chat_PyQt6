"""Best bounce count of the pets per account: one number in data/pet_records.json."""

from __future__ import annotations

from core.state.user_state import ByUserStore


MINIMUM_RECORD = 5  # fewer bounces in one throw are not worth a record


class PetRecords:
    """The most bounces one throw has made, remembered per username."""

    _store = ByUserStore("pet_records.json")

    def get(self, username: str) -> int:
        """Return the record of the account, zero when there is none."""
        return int(self._store.get(username) or 0)

    def reset(self, username: str) -> None:
        """Forget the record of one account."""
        self._store.set(username, None)

    def reset_all(self) -> None:
        """Forget the records of all accounts."""
        self._store.clear()

    def submit(self, username: str, bounces: int) -> int | None:
        """Save bounces as the new record and return the beaten one (zero for the first), or None when it is no record."""
        previous = self.get(username)
        if not username or bounces < MINIMUM_RECORD or bounces <= previous:
            return None
        self._store.set(username, bounces)
        return previous
