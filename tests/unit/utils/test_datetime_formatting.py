from datetime import datetime, timezone

from src.api.utils.api_responses import SuccessResponseModel
from src.utils import format_datetime


def test_format_datetime_outputs_expected_layout_for_naive_value():
    value = datetime(2026, 4, 7, 17, 3, 20)

    assert format_datetime(value) == "07-04-2026 18:03:20"


def test_response_model_timestamp_serializer_uses_shared_datetime_format():
    value = datetime(2026, 4, 7, 17, 3, 20, tzinfo=timezone.utc)
    response = SuccessResponseModel(message="ok", timestamp=value)

    dumped = response.model_dump(mode="json")

    assert dumped["timestamp"] == "07-04-2026 18:03:20"

