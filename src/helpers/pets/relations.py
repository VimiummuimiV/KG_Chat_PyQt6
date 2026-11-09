"""Who hunts and who guards against whom among the pet species."""

from helpers.pets.catalog import PetKind


_PREY = {"fox": frozenset({"chicken"})}  # predator species -> species it hunts
_GUARDED_AGAINST = {"dog": frozenset({"fox"})}  # guard species -> predator species it drives off


PREDATOR_SPECIES = frozenset(_PREY)


def preys_on(predator: PetKind, prey: PetKind) -> bool:
    """Whether pets of the predator kind hunt pets of the prey kind."""
    return prey.species in _PREY.get(predator.species, ())


def guards_against(guard: PetKind, predator: PetKind) -> bool:
    """Whether pets of the guard kind drive off pets of the predator kind."""
    return predator.species in _GUARDED_AGAINST.get(guard.species, ())
