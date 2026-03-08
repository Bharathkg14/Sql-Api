import pytest
from pydantic import ValidationError
from app.schemas import MeasureModel, FilterModel, SortModel, GetDataParams, QueryResponse, FilterCondition

def test_measure_model_valid():
    model = MeasureModel(field="test_field", function="sum")
    assert model.function == "SUM"  # Normalized to uppercase

def test_measure_model_invalid_function():
    with pytest.raises(ValidationError) as exc:
        MeasureModel(field="test_field", function="invalid")
    assert "Function must be one of" in str(exc.value)

@pytest.mark.parametrize("operator, values, should_raise", [
    ("equal", 42, False),
    ("in", [1, 2, 3], False),
    ("between", [10, 20], False),
    ("equal", [42], True),
    ("between", [10], True),
    ("invalid_op", 42, True),
])
def test_filter_model_validation(operator, values, should_raise):
    if should_raise:
        with pytest.raises(ValidationError):
            FilterModel(field="test_field", operator=operator, values=values)
    else:
        model = FilterModel(field="test_field", operator=operator, values=values)
        assert model.operator.isupper()  # Normalized

def test_sort_model_valid():
    model = SortModel(field="test_field", order="desc")
    assert model.order == "DESC"

def test_sort_model_invalid_order():
    with pytest.raises(ValidationError):
        SortModel(field="test_field", order="invalid")

def test_get_data_params_methods(sample_get_data_params):
    params = sample_get_data_params
    assert params.is_aggregated() is True
    assert params.is_distinct_only() is False
    assert set(params.get_all_columns()) == {"newpnl", "uidtype", "businessdate"}

def test_get_data_params_invalid_page():
    with pytest.raises(ValidationError):
        GetDataParams(page=0)

def test_legacy_filter_condition():
    # Test backward compatibility
    condition = FilterCondition(field="test", operator="equal", values=42)
    assert condition.operator == "EQUAL"

def test_query_response_structure():
    response = QueryResponse(
        query_id="test_id",
        data=[{"key": "value"}],
        page=1,
        page_size=10,
        total_count=1,
        query="SELECT * FROM test"
    )
    assert isinstance(response.data, list)
    assert response.total_count == 1