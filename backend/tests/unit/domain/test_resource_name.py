"""The framework's one name rule.

``ResourceRef`` used to enforce this in its constructor, which meant the rule
was enforced wherever an identifier was BUILT rather than wherever a name was
WRITTEN — and the rename path, which lived in one kind's service, built no ref
and so checked something else entirely. The rule now lives in one function that
registration and rename both call.

The rule itself is unchanged, and deliberately so. The identity no longer needs
a name to be a safe path segment, but `skill`, `knowledge` and `memory` each
turn a name into a directory, so relaxing it framework-wide would free four
kinds and leave three behind.
"""

import pytest

from coffer.domain.resource import InvalidResourceNameError, validate_resource_name


@pytest.mark.parametrize(
    "invalid",
    [
        "bad name",  # space
        "bad/name",  # slash — would escape a single path segment
        "café",  # non-ASCII
        "bad!name",
        "bad@name",
        "",  # empty
    ],
)
def test_rejects_a_name_that_is_not_one_safe_segment(invalid):
    with pytest.raises(InvalidResourceNameError):
        validate_resource_name(invalid)


def test_rejects_a_name_over_64_characters():
    with pytest.raises(InvalidResourceNameError):
        validate_resource_name("a" * 65)


@pytest.mark.parametrize(
    "valid", ["simple", "with-dash", "with_underscore", "with.dot", "ABC123", "a" * 64]
)
def test_accepts_letters_digits_underscore_dot_and_hyphen(valid):
    validate_resource_name(valid)  # does not raise


def test_the_error_is_a_value_error():
    """Callers catch ``ValueError`` to convert it into their own envelope —
    ``ResourceService`` turns it into ``ConfigValidationError``."""
    assert issubclass(InvalidResourceNameError, ValueError)
