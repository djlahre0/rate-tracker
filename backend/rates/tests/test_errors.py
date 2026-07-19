from rest_framework.exceptions import NotFound, ValidationError

from rates.errors import structured_exception_handler


def test_unexpected_exception_returns_structured_500_not_a_stack():
    response = structured_exception_handler(ValueError("boom"), {"request": None})
    assert response.status_code == 500
    assert response.data == {
        "error": "internal_error",
        "detail": "An unexpected error occurred.",
        "fields": None,
    }


def test_handled_non_400_has_no_fields():
    response = structured_exception_handler(NotFound("nope"), {"request": None})
    assert response.status_code == 404
    assert response.data["error"] == "request_failed"
    assert response.data["fields"] is None


def test_400_with_list_body_is_labeled_validation_error():
    # A ValidationError raised with a string/list detail renders as a top-level list;
    # it must still get the consistent 400 contract (validation_error + fields).
    response = structured_exception_handler(ValidationError(["bad thing"]), {"request": None})
    assert response.status_code == 400
    assert response.data["error"] == "validation_error"
    assert response.data["fields"] == {"non_field_errors": ["bad thing"]}
