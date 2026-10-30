"""
Unit tests for the object storage key helpers.
"""

import uuid

from src.uploads.storage.keys import chat_session_prefix, document_object_key


def test_document_key_starts_with_its_chat_session_prefix():
    chat_session_id, document_id = uuid.uuid4(), uuid.uuid4()

    key = document_object_key(chat_session_id, document_id)

    assert key == f"{chat_session_id}/{document_id}"
    assert key.startswith(chat_session_prefix(chat_session_id))


def test_prefix_does_not_match_another_session_with_a_shared_start():
    chat_session_id = uuid.uuid4()
    lookalike = f"{chat_session_id}0/{uuid.uuid4()}"

    # The trailing slash keeps a delete of one session's prefix from matching
    # keys that only share its leading characters
    assert not lookalike.startswith(chat_session_prefix(chat_session_id))
