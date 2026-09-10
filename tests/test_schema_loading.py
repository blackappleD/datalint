"""外部 schema 文件加载与自校验单元测试(含全部非法 schema 类别)."""

import pytest

from datalint.schema import FieldSpec, SchemaValidationError, load_schema


def valid_schema_obj():
    return {
        "fields": [
            {"name": "user_id", "type": "string", "required": True},
            {"name": "level", "type": "enum", "required": True, "enum_values": ["gold", "silver"]},
            {"name": "amount", "type": "number"},
            {"name": "created_at", "type": "timestamp", "required": True},
        ]
    }


# ---------- 合法 schema ----------


def test_valid_schema_loads_as_fieldspec_tuple(write_schema):
    path = write_schema(valid_schema_obj())

    schema = load_schema(path)

    assert isinstance(schema, tuple)
    assert all(isinstance(spec, FieldSpec) for spec in schema)
    assert [spec.name for spec in schema] == ["user_id", "level", "amount", "created_at"]
    assert schema[1].enum_values == frozenset({"gold", "silver"})


def test_required_defaults_to_false(write_schema):
    path = write_schema(valid_schema_obj())

    schema = load_schema(path)

    amount = next(spec for spec in schema if spec.name == "amount")
    assert amount.required is False


# ---------- 非法 schema: 每类断言报错含定位信息 ----------


def rejects(write_schema, obj, *needles):
    path = write_schema(obj)
    with pytest.raises(SchemaValidationError) as exc_info:
        load_schema(path)
    message = str(exc_info.value)
    for needle in needles:
        assert needle in message, f"错误信息缺少 {needle!r}: {message}"


def test_invalid_json_syntax(write_schema):
    rejects(write_schema, '{"fields": [', "JSON")


def test_top_level_not_object(write_schema):
    rejects(write_schema, "[1, 2]", "对象")


def test_missing_fields_key(write_schema):
    rejects(write_schema, {"columns": []}, "fields")


def test_fields_not_a_list(write_schema):
    rejects(write_schema, {"fields": {"name": "a"}}, "fields")


def test_fields_empty(write_schema):
    rejects(write_schema, {"fields": []}, "fields")


def test_field_missing_name(write_schema):
    rejects(write_schema, {"fields": [{"type": "string"}]}, "name")


def test_field_name_empty(write_schema):
    rejects(write_schema, {"fields": [{"name": "", "type": "string"}]}, "name")


def test_field_name_not_string(write_schema):
    rejects(write_schema, {"fields": [{"name": 1, "type": "string"}]}, "name")


def test_duplicate_field_names(write_schema):
    rejects(
        write_schema,
        {"fields": [{"name": "a", "type": "string"}, {"name": "a", "type": "number"}]},
        "a",
        "重复",
    )


def test_missing_type(write_schema):
    rejects(write_schema, {"fields": [{"name": "a"}]}, "a", "type")


def test_unsupported_type_lists_supported(write_schema):
    rejects(
        write_schema,
        {"fields": [{"name": "a", "type": "datetime"}]},
        "a",
        "datetime",
        "string",
        "number",
        "timestamp",
        "enum",
    )


def test_required_not_bool(write_schema):
    rejects(
        write_schema,
        {"fields": [{"name": "a", "type": "string", "required": "yes"}]},
        "a",
        "required",
    )


def test_enum_without_values(write_schema):
    rejects(write_schema, {"fields": [{"name": "a", "type": "enum"}]}, "a", "enum_values")


def test_enum_values_empty(write_schema):
    rejects(
        write_schema,
        {"fields": [{"name": "a", "type": "enum", "enum_values": []}]},
        "a",
        "enum_values",
    )


def test_enum_values_non_string(write_schema):
    rejects(
        write_schema,
        {"fields": [{"name": "a", "type": "enum", "enum_values": ["x", 1]}]},
        "a",
        "enum_values",
    )


def test_non_enum_with_enum_values(write_schema):
    rejects(
        write_schema,
        {"fields": [{"name": "a", "type": "string", "enum_values": ["x"]}]},
        "a",
        "enum_values",
    )


def test_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        load_schema(tmp_path / "nope.json")
