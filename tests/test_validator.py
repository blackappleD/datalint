"""validator 模块单元测试: 必填/类型/枚举校验."""

from datalint.schema import ENUM_ERROR, MISSING_FIELD, TYPE_ERROR, Rejection
from datalint.validator import validate


def valid_record(**overrides):
    record = {
        "id": "1",
        "name": "Alice",
        "category": "A",
        "score": 1.5,
        "timestamp": "2026-09-10T08:00:00Z",
    }
    record.update(overrides)
    return record


def test_valid_record_passes():
    assert validate(1, valid_record()) is None


def test_optional_field_may_be_absent():
    record = valid_record()
    del record["score"]

    assert validate(1, record) is None


def test_missing_required_field_reports_field_name():
    record = valid_record()
    del record["name"]

    rejection = validate(3, record)

    assert isinstance(rejection, Rejection)
    assert rejection.line == 3
    assert rejection.error_type == MISSING_FIELD
    assert "name" in rejection.reason


def test_type_error_reports_expected_and_actual():
    rejection = validate(1, valid_record(score="high"))

    assert rejection.error_type == TYPE_ERROR
    assert "score" in rejection.reason
    assert "number" in rejection.reason
    assert "str" in rejection.reason


def test_bool_is_not_a_number():
    rejection = validate(1, valid_record(score=True))

    assert rejection is not None
    assert rejection.error_type == TYPE_ERROR


def test_bool_is_not_a_timestamp():
    rejection = validate(1, valid_record(timestamp=True))

    assert rejection is not None
    assert rejection.error_type == TYPE_ERROR


def test_numeric_timestamp_passes_type_check():
    assert validate(1, valid_record(timestamp=1789027200)) is None


def test_enum_value_not_allowed_reports_value():
    rejection = validate(1, valid_record(category="X"))

    assert rejection.error_type == ENUM_ERROR
    assert "category" in rejection.reason
    assert "X" in rejection.reason


def test_enum_must_be_string():
    rejection = validate(1, valid_record(category=1))

    assert rejection.error_type == TYPE_ERROR


def test_unknown_fields_are_ignored():
    assert validate(1, valid_record(extra="  anything  ", another=[1, 2])) is None


def test_first_error_only_by_schema_order():
    # 同时缺 id(schema 第 1 个字段)且 category 非法 → 只报 id 缺失
    record = valid_record(category="X")
    del record["id"]

    rejection = validate(1, record)

    assert rejection.error_type == MISSING_FIELD
    assert "id" in rejection.reason
