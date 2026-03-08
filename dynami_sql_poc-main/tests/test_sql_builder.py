import pytest
import yaml
from unittest.mock import patch, MagicMock, create_autospec, Mock
from app.sql_builder import SQLBuilder, ValidationError, TableConfig, JoinRelation
from app.schemas import GetDataParams, MeasureModel, FilterModel, SortModel

# Basic initialization tests
def test_yaml_fixture(sample_table_config_yaml):
    parsed_yaml = yaml.safe_load(sample_table_config_yaml)
    assert parsed_yaml is not None
    assert "SCHEMAS" in parsed_yaml
    assert "newwpnl" in parsed_yaml["SCHEMAS"]

def test_sql_builder_init_with_config(mock_yaml_load):
    builder = SQLBuilder()
    assert "newwpnl" in builder.table_configs
    assert builder.table_configs["newwpnl"].priority == 1
    assert "uid" in builder.table_configs["newwpnl"].restricted_attributes
    assert builder.count_strategy == "simple"


def test_sql_builder_init_without_config():
    with patch('os.path.exists', return_value=False):
        builder = SQLBuilder()
        assert len(builder.table_configs) == 0


def test_sql_builder_init_with_error():
    with patch('builtins.open', side_effect=Exception("File error")), \
            patch('os.path.exists', return_value=True):
        builder = SQLBuilder()
        assert len(builder.table_configs) == 0


def test_sql_builder_init_custom_strategy():
    with patch('os.path.exists', return_value=False):
        builder = SQLBuilder(count_strategy="distinct")
        assert builder.count_strategy == "distinct"

# TableConfig and JoinRelation tests
def test_table_config_creation():
    config = TableConfig(
        name="test_table",
        priority=1,
        columns=[{"name": "col1", "field_type": "VARCHAR"}],
        relations=[{"name": "rel1"}],
        mandatory_fields=["col1"],
        aggregations=[{"field": "col2", "function": "SUM"}],
        restricted_attributes=["col3"]
    )
    assert config.name == "test_table"
    assert config.priority == 1
    assert len(config.columns) == 1
    assert len(config.relations) == 1
    assert config.mandatory_fields == ["col1"]
    assert len(config.aggregations) == 1
    assert config.restricted_attributes == ["col3"]


def test_join_relation_creation():
    relation = JoinRelation(
        target_table="users",
        join_type="LEFT",
        join_columns=[{"source": "uid", "target": "id"}]
    )
    assert relation.target_table == "users"
    assert relation.join_type == "LEFT"
    assert len(relation.join_columns) == 1


# Column validation tests
def test_validate_columns_valid(mock_yaml_load):
    builder = SQLBuilder()
    errors = builder._validate_columns(["uidtype", "newpnl"])
    assert not errors


def test_validate_columns_with_table_prefix_valid(mock_yaml_load):
    builder = SQLBuilder()
    errors = builder._validate_columns(["newwpnl.uidtype", "users.name"])
    assert not errors


def test_validate_columns_invalid(mock_yaml_load):
    builder = SQLBuilder()
    errors = builder._validate_columns(["nonexistent_col"])
    assert len(errors) == 1
    assert "Column 'nonexistent_col' not found in any table" in errors[0]["message"]


def test_validate_columns_with_invalid_table(mock_yaml_load):
    builder = SQLBuilder()
    errors = builder._validate_columns(["invalid_table.col"])
    assert len(errors) == 1
    assert "Table 'invalid_table' in column 'invalid_table.col' not found" in errors[0]["message"]


def test_validate_columns_with_invalid_column_in_valid_table(mock_yaml_load):
    builder = SQLBuilder()
    errors = builder._validate_columns(["newwpnl.invalid_col"])
    assert len(errors) == 1
    assert "Column 'newwpnl.invalid_col' does not exist in table 'newwpnl'" in errors[0]["message"]


def test_validate_columns_with_aliases(mock_yaml_load):
    builder = SQLBuilder()
    errors = builder._validate_columns(["user_type", "profit_loss"])  # using aliases
    assert not errors


# Data type validation tests
def test_validate_filter_data_types_valid(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(filterBy=[
        FilterModel(field="uidtype", operator="EQUAL", values="test"),
        FilterModel(field="businessdate", operator="BETWEEN", values=[20230101, 20230201]),
        FilterModel(field="uid", operator="IN", values=[1, 2, 3])
    ])
    _, column_to_table_map = builder._get_explicitly_requested_tables(params)
    errors = builder._validate_filter_data_types(params.filterBy, column_to_table_map)
    assert not errors


def test_validate_filter_data_types_invalid_type(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(filterBy=[
        FilterModel(field="uid", operator="EQUAL", values="should_be_int")
    ])
    _, column_to_table_map = builder._get_explicitly_requested_tables(params)
    errors = builder._validate_filter_data_types(params.filterBy, column_to_table_map)
    assert len(errors) == 1
    assert "Invalid data type" in errors[0]["message"]

def test_validate_filter_data_types_invalid_in(mock_yaml_load):
    builder = SQLBuilder()

    with patch("app.schemas.FilterModel", autospec=True) as MockFilterModel:
        mock_instance = create_autospec(FilterModel, instance=True)
        mock_instance.field = "uid"
        mock_instance.operator = "IN"
        mock_instance.values = []
        MockFilterModel.return_value = mock_instance

        params = GetDataParams(filterBy=[mock_instance])
        _, column_to_table_map = builder._get_explicitly_requested_tables(params)
        errors = builder._validate_filter_data_types(params.filterBy, column_to_table_map)

        assert len(errors) == 1
        assert "must be a non-empty list" in errors[0]["message"]

def test_validate_filter_data_types_unsupported_operator(mock_yaml_load):
    builder = SQLBuilder()

    with patch("app.schemas.FilterModel", autospec=True) as MockFilterModel:
        mock_instance = create_autospec(FilterModel, instance=True)
        mock_instance.field = "uid"
        mock_instance.operator = "LIKE"
        mock_instance.values = "test"
        MockFilterModel.return_value = mock_instance

        params = GetDataParams(filterBy=[mock_instance])
        _, column_to_table_map = builder._get_explicitly_requested_tables(params)
        errors = builder._validate_filter_data_types(params.filterBy, column_to_table_map)

        assert len(errors) == 1
        assert "Unsupported operator 'LIKE'" in errors[0]["message"]


def test_validate_filter_data_types_invalid_filter_model(mock_yaml_load):
    builder = SQLBuilder()
    mock_params = MagicMock(spec=GetDataParams)
    mock_params.filterBy = ["invalid_filter"]
    mock_params.__pydantic_fields_set__ = {"filterBy"}

    with patch("app.schemas.GetDataParams", return_value=mock_params) as mock_get_data_params:
        _, column_to_table_map = builder._get_explicitly_requested_tables(mock_params)
        errors = builder._validate_filter_data_types(mock_params.filterBy, column_to_table_map)

        assert len(errors) == 1
        assert "not a valid FilterModel" in errors[0]["message"]

# Measure validation tests
def test_validate_measures_valid(mock_yaml_load):
    builder = SQLBuilder()
    errors = builder._validate_measures([
        MeasureModel(field="newpnl", function="SUM")
    ])
    assert not errors


def test_validate_measures_invalid_function(mock_yaml_load):
    builder = SQLBuilder()

    with patch("app.schemas.MeasureModel", autospec=True) as MockMeasureModel:
        mock_instance = create_autospec(MeasureModel, instance=True)
        mock_instance.field = "newpnl"
        mock_instance.function = "INVALID"
        MockMeasureModel.return_value = mock_instance

        errors = builder._validate_measures([mock_instance])

        assert len(errors) == 1
        assert "Invalid aggregation function" in errors[0]["message"]


def test_validate_measures_unsupported_function_for_field(mock_yaml_load):
    builder = SQLBuilder()
    errors = builder._validate_measures([
        MeasureModel(field="uid", function="SUM")  # uid only supports EQUAL, IN
    ])
    assert len(errors) == 1
    assert "is not supported for field" in errors[0]["message"]


def test_validate_measures_invalid_field(mock_yaml_load):
    builder = SQLBuilder()
    errors = builder._validate_measures([
        MeasureModel(field="nonexistent", function="SUM")
    ])
    assert len(errors) == 1
    assert "not found in any table" in errors[0]["message"]

# Query building tests - Basic SELECT
def test_build_query_simple_select(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["uidtype"])
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SELECT DISTINCT uidtype" in main_query
    assert "FROM newwpnl" in main_query
    assert main_params == []

def test_build_query_with_table_prefix(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["newwpnl.uidtype"])
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SELECT DISTINCT uidtype" in main_query
    assert "FROM newwpnl" in main_query


# Query building tests - Aggregated
def test_build_query_aggregated(mock_yaml_load):
    builder = SQLBuilder(count_strategy="simple")
    params = GetDataParams(
        measures=[MeasureModel(field="newpnl", function="SUM")],
        groupBy=["uidtype"],
        filterBy=[FilterModel(field="businessdate", operator="EQUAL", values=20230101)],
        sortBy=[SortModel(field="newpnl", order="DESC")],
        page=1,
        page_size=10
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SELECT uidtype, businessdate" in main_query
    assert "SUM(newpnl) AS sum_newpnl" in main_query
    assert "FROM newwpnl" in main_query
    assert "WHERE (businessdate = ?)" in main_query
    assert "GROUP BY uidtype, businessdate" in main_query
    assert "ORDER BY newpnl DESC" in main_query
    assert "LIMIT 10" in main_query
    assert main_params == [20230101]


def test_build_query_multiple_measures(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        measures=[
            MeasureModel(field="newpnl", function="SUM"),
            MeasureModel(field="newpnl", function="AVG")
        ],
        groupBy=["uidtype"]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SUM(newpnl) AS sum_newpnl" in main_query
    assert "AVG(newpnl) AS avg_newpnl" in main_query


# Query building tests - DISTINCT
def test_build_query_distinct(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["uidtype"], distinct=True)
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SELECT DISTINCT uidtype" in main_query


def test_build_query_distinct_multiple_columns(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["uidtype", "businessdate"], distinct=True)
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SELECT DISTINCT uidtype, businessdate" in main_query


# Query building tests - Filters
def test_build_query_equal_filter(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["uidtype"],
        filterBy=[FilterModel(field="businessdate", operator="EQUAL", values=20230101)]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "WHERE (businessdate = ?)" in main_query
    assert main_params == [20230101]


def test_build_query_in_filter(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["uidtype"],
        filterBy=[FilterModel(field="uid", operator="IN", values=[1, 2, 3])]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "WHERE (uid IN (?,?,?))" in main_query
    assert main_params == [1, 2, 3]


def test_build_query_between_filter(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["uidtype"],
        filterBy=[FilterModel(field="businessdate", operator="BETWEEN", values=[20230101, 20230201])]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "WHERE (businessdate BETWEEN ? AND ?)" in main_query
    assert main_params == [20230101, 20230201]


def test_build_query_multiple_filters(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["uidtype"],
        filterBy=[
            FilterModel(field="businessdate", operator="EQUAL", values=20230101),
            FilterModel(field="uid", operator="IN", values=[1, 2])
        ]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "WHERE (businessdate = ? AND uid IN (?,?))" in main_query
    assert main_params == [20230101, 1, 2]


# Query building tests - Sorting
def test_build_query_single_sort(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["uidtype"],
        sortBy=[SortModel(field="uidtype", order="ASC")]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "ORDER BY uidtype ASC" in main_query


def test_build_query_multiple_sort(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["uidtype", "businessdate"],
        sortBy=[
            SortModel(field="uidtype", order="ASC"),
            SortModel(field="businessdate", order="DESC")
        ]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "ORDER BY uidtype ASC, businessdate DESC" in main_query


# Query building tests - Pagination
def test_build_query_pagination(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["uidtype"],
        page=2,
        page_size=10
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "LIMIT 10" in main_query
    assert "OFFSET 10" in main_query


def test_build_query_pagination_first_page(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["uidtype"],
        page=1,
        page_size=10
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "LIMIT 10" in main_query
    assert "OFFSET" not in main_query


# JOIN tests
def test_build_query_with_joins(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["newwpnl.uidtype", "users.name"]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "FROM newwpnl" in main_query
    assert "LEFT JOIN users ON newwpnl.uid = users.id" in main_query


def test_build_query_multiple_joins(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["newwpnl.uidtype", "users.name", "profile.email"]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "FROM newwpnl" in main_query
    assert "LEFT JOIN users ON newwpnl.uid = users.id" in main_query
    assert "LEFT JOIN profile ON users.id = profile.id" in main_query


# Count query tests
def test_build_count_query_simple_strategy(mock_yaml_load):
    builder = SQLBuilder(count_strategy="simple")
    params = GetDataParams(groupBy=["uidtype"])
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SELECT COUNT(*)" in count_query
    assert "FROM newwpnl" in count_query


def test_build_count_query_distinct_strategy(mock_yaml_load):
    builder = SQLBuilder(count_strategy="distinct")
    params = GetDataParams(groupBy=["uidtype"], distinct=True)
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "COUNT(DISTINCT uidtype)" in count_query


def test_build_count_query_distinct_strategy_multiple_columns(mock_yaml_load):
    builder = SQLBuilder(count_strategy="distinct")
    params = GetDataParams(groupBy=["uidtype", "businessdate"], distinct=True)
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "COUNT(DISTINCT (uidtype || '|' || businessdate))" in count_query


def test_build_count_query_separate_strategy(mock_yaml_load):
    builder = SQLBuilder(count_strategy="separate")
    params = GetDataParams(groupBy=["uidtype"])
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SELECT DISTINCT uidtype" in count_query


def test_build_count_query_estimate_strategy(mock_yaml_load):
    builder = SQLBuilder(count_strategy="estimate")
    params = GetDataParams(groupBy=["uidtype"])
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SELECT -1 AS estimated_count" in count_query
    assert count_params == []


def test_build_count_query_unknown_strategy(mock_yaml_load):
    builder = SQLBuilder(count_strategy="unknown")
    params = GetDataParams(groupBy=["uidtype"])
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SELECT COUNT(*)" in count_query


# Count result processing tests
def test_get_count_from_results_simple(mock_yaml_load):
    builder = SQLBuilder(count_strategy="simple")
    count_result = [{"count": 100}]
    main_results = []
    params = GetDataParams()

    count = builder.get_count_from_results(count_result, main_results, params)
    assert count == 100


def test_get_count_from_results_separate(mock_yaml_load):
    builder = SQLBuilder(count_strategy="separate")
    count_result = [{"uidtype": "A"}, {"uidtype": "B"}, {"uidtype": "C"}]
    main_results = []
    params = GetDataParams()

    count = builder.get_count_from_results(count_result, main_results, params)
    assert count == 3


def test_get_count_from_results_estimate_with_pagination(mock_yaml_load):
    builder = SQLBuilder(count_strategy="estimate")
    count_result = [{"estimated_count": -1}]
    main_results = [{"row": i} for i in range(10)]  # Full page
    params = GetDataParams(page=2, page_size=10)

    count = builder.get_count_from_results(count_result, main_results, params)
    assert count == 30  # 2 * 10 + 10


def test_get_count_from_results_estimate_partial_page(mock_yaml_load):
    builder = SQLBuilder(count_strategy="estimate")
    count_result = [{"estimated_count": -1}]
    main_results = [{"row": i} for i in range(5)]
    params = GetDataParams(page=2, page_size=10)

    count = builder.get_count_from_results(count_result, main_results, params)
    assert count == 15


def test_get_count_from_results_empty(mock_yaml_load):
    builder = SQLBuilder()
    count_result = []
    main_results = []
    params = GetDataParams()

    count = builder.get_count_from_results(count_result, main_results, params)
    assert count == 0


# Distinct values query tests
def test_build_distinct_values_query_valid(mock_yaml_load):
    builder = SQLBuilder()
    queries = builder.build_distinct_values_query(["uidtype"])

    assert len(queries) == 1
    assert queries[0][0] == "uidtype"
    assert queries[0][1] == "VARCHAR"
    assert "SELECT DISTINCT uidtype FROM newwpnl WHERE uidtype IS NOT NULL" in queries[0][2]
    assert queries[0][3] == []


def test_build_distinct_values_query_with_table_prefix(mock_yaml_load):
    builder = SQLBuilder()
    queries = builder.build_distinct_values_query(["newwpnl.uidtype"])

    assert len(queries) == 1
    assert queries[0][0] == "newwpnl.uidtype"
    assert "SELECT DISTINCT uidtype FROM newwpnl WHERE uidtype IS NOT NULL" in queries[0][2]


def test_build_distinct_values_query_restricted(mock_yaml_load):
    builder = SQLBuilder()
    queries = builder.build_distinct_values_query(["uid"])

    assert len(queries) == 1
    assert queries[0][0] == "uid"
    assert queries[0][2] is None
    assert queries[0][3] == []


def test_build_distinct_values_query_multiple_columns(mock_yaml_load):
    builder = SQLBuilder()
    queries = builder.build_distinct_values_query(["uidtype", "uid"])

    assert len(queries) == 2
    assert queries[0][0] == "uidtype"
    assert queries[0][2] is not None
    assert queries[1][0] == "uid"
    assert queries[1][2] is None


def test_build_distinct_values_query_invalid_column(mock_yaml_load):
    builder = SQLBuilder()

    with pytest.raises(ValidationError) as exc:
        builder.build_distinct_values_query(["invalid_column"])

    assert len(exc.value.errors) == 1
    assert "not found in any table" in exc.value.errors[0]["message"]


# Validation error tests
def test_build_query_validation_error(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(measures=[MeasureModel(field="nonexistent", function="SUM")])

    with pytest.raises(ValidationError) as exc:
        builder.build_query(params)

    assert len(exc.value.errors) >= 1


def test_build_query_multiple_validation_errors(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        measures=[MeasureModel(field="nonexistent", function="SUM")],
        filterBy=[FilterModel(field="invalid", operator="EQUAL", values="test")]
    )

    with pytest.raises(ValidationError) as exc:
        builder.build_query(params)

    assert len(exc.value.errors) >= 2


# Helper method tests
def test_get_column_data_type(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["uidtype"])
    _, column_to_table_map = builder._get_explicitly_requested_tables(params)

    data_type = builder._get_column_data_type("uidtype", column_to_table_map)
    assert data_type == "VARCHAR"


def test_get_column_data_type_with_prefix(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["newwpnl.uidtype"])
    _, column_to_table_map = builder._get_explicitly_requested_tables(params)

    data_type = builder._get_column_data_type("newwpnl.uidtype", column_to_table_map)
    assert data_type == "VARCHAR"


def test_get_column_data_type_unknown(mock_yaml_load):
    builder = SQLBuilder()
    column_to_table_map = {}

    data_type = builder._get_column_data_type("unknown", column_to_table_map)
    assert data_type is None


def test_get_supported_operators(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["uidtype"])
    _, column_to_table_map = builder._get_explicitly_requested_tables(params)

    operators = builder._get_supported_operators("uidtype", column_to_table_map)
    assert "EQUAL" in operators
    assert "IN" in operators


def test_determine_main_table_empty(mock_yaml_load):
    builder = SQLBuilder()

    with pytest.raises(ValidationError) as exc:
        builder._determine_main_table({})

    assert "No tables found" in exc.value.errors[0]["message"]


def test_determine_main_table_priority(mock_yaml_load):
    builder = SQLBuilder()
    tables = {
        "newwpnl": builder.table_configs["newwpnl"],
        "users": builder.table_configs["users"]
    }

    main_table = builder._determine_main_table(tables)
    assert main_table.name == "newwpnl"


def test_convert_join_type(mock_yaml_load):
    builder = SQLBuilder()

    assert builder._convert_join_type("ONE_TO_ONE") == "LEFT"
    assert builder._convert_join_type("INNER") == "INNER"
    assert builder._convert_join_type("RIGHT") == "RIGHT"
    assert builder._convert_join_type("OUTER") == "FULL OUTER"
    assert builder._convert_join_type("UNKNOWN") == "LEFT"

# Edge cases and complex scenarios
def test_build_query_with_aliases(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["user_type"],
        measures=[MeasureModel(field="profit_loss", function="SUM")]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "uidtype" in main_query
    assert "SUM(newpnl)" in main_query


def test_build_query_aggregated_without_group_by(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        measures=[MeasureModel(field="newpnl", function="SUM")]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SUM(newpnl)" in main_query
    assert "GROUP BY" in main_query


def test_build_query_with_table_aggregations(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        groupBy=["uidtype"],
        measures=[MeasureModel(field="newpnl", function="SUM")]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "SUM(newpnl) AS total_newpnl" in main_query


def test_build_query_mandatory_fields_in_select(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        measures=[MeasureModel(field="newpnl", function="SUM")],
        groupBy=["uidtype"]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "uidtype" in main_query
    assert "businessdate" in main_query


def test_build_query_mandatory_fields_in_group_by(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        measures=[MeasureModel(field="newpnl", function="SUM")]
    )
    main_query, main_params, count_query, count_params = builder.build_query(params)

    assert "GROUP BY uidtype, businessdate" in main_query


def test_build_filter_condition_null_values(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["uidtype"])

    filter_obj = FilterModel(field="businessdate", operator="BETWEEN", values=[None, 20230201])
    condition, params_list = builder._build_filter_condition(filter_obj)
    assert condition == "businessdate BETWEEN ? AND ?"
    assert params_list == [None, 20230201]


def test_build_filter_condition_invalid_operator(mock_yaml_load):
    builder = SQLBuilder()

    filter_obj = Mock(spec=['field', 'operator', 'values'])
    filter_obj.field = "businessdate"
    filter_obj.operator = "INVALID"
    filter_obj.values = 123

    condition, params_list = builder._build_filter_condition(filter_obj)
    assert condition is None
    assert params_list == []

def test_find_tables_to_join_complex(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["newwpnl.uidtype", "users.name", "profile.email"])
    set_a_tables, _ = builder._get_explicitly_requested_tables(params)

    join_tables = builder._find_tables_to_join(set_a_tables)

    assert "newwpnl" in join_tables
    assert "users" in join_tables
    assert "profile" in join_tables


def test_find_join_path_no_path(mock_yaml_load):
    builder = SQLBuilder()
    orphan_table = TableConfig("orphan", 999, [])
    joined_tables = {"newwpnl": builder.table_configs["newwpnl"]}

    join_clause = builder._find_join_path(orphan_table, joined_tables)
    assert join_clause is None


def test_build_join_clause_dict_format(mock_yaml_load):
    builder = SQLBuilder()
    source_config = builder.table_configs["newwpnl"]
    target_config = builder.table_configs["users"]

    relation = {
        "type": "LEFT",
        "joinColumns": [
            {"source": "uid", "target": "id"},
            {"name": "common_field"}
        ]
    }

    join_clause = builder._build_join_clause(source_config, target_config, relation)
    assert "newwpnl.uid = users.id" in join_clause
    assert "newwpnl.common_field = users.common_field" in join_clause


def test_build_join_clause_string_format(mock_yaml_load):
    builder = SQLBuilder()
    source_config = builder.table_configs["newwpnl"]
    target_config = builder.table_configs["users"]

    relation = {
        "type": "INNER",
        "joinColumns": ["common_field"]
    }

    join_clause = builder._build_join_clause(source_config, target_config, relation)
    assert "INNER JOIN users ON newwpnl.common_field = users.common_field" in join_clause


def test_build_join_clause_no_conditions(mock_yaml_load):
    builder = SQLBuilder()
    source_config = builder.table_configs["newwpnl"]
    target_config = builder.table_configs["users"]

    relation = {"type": "LEFT", "joinColumns": []}

    join_clause = builder._build_join_clause(source_config, target_config, relation)
    assert join_clause is None


def test_get_reverse_relations_for_table(mock_yaml_load):
    builder = SQLBuilder()
    users_config = builder.table_configs["users"]

    reverse_relations = builder._get_reverse_relations_for_table(users_config)

    assert len(reverse_relations) == 1
    assert reverse_relations[0]["source_table"] == "newwpnl"
    assert reverse_relations[0]["target_table"] == "users"


def test_build_join_clause_from_reverse(mock_yaml_load):
    builder = SQLBuilder()
    target_config = builder.table_configs["users"]
    source_config = builder.table_configs["newwpnl"]

    reverse_relation = {
        "source_table": "newwpnl",
        "target_table": "users",
        "original_relation": {
            "type": "LEFT",
            "joinColumns": [{"source": "uid", "target": "id"}]
        }
    }

    join_clause = builder._build_join_clause_from_reverse(target_config, source_config, reverse_relation)
    assert "LEFT JOIN users ON newwpnl.id = users.uid" in join_clause


def test_reset_query_parts(mock_yaml_load):
    builder = SQLBuilder()

    builder.query_parts['select'] = ["test"]
    builder.parameters = [123]

    builder._reset()

    assert builder.query_parts['select'] == []
    assert builder.parameters == []
    assert builder.query_parts['from'] == ''


def test_get_explicitly_requested_tables_priority(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["id"])

    set_a_tables, column_to_table_map = builder._get_explicitly_requested_tables(params)

    assert column_to_table_map["id"].name == "users"


def test_get_explicitly_requested_tables_case_insensitive(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["NEWWPNL.uidtype"])

    set_a_tables, column_to_table_map = builder._get_explicitly_requested_tables(params)

    assert "NEWWPNL" in set_a_tables
    assert column_to_table_map["uidtype"].name == "newwpnl"


def test_get_explicitly_requested_tables_unknown_table(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["unknown_table.col"])

    set_a_tables, column_to_table_map = builder._get_explicitly_requested_tables(params)

    assert "unknown_table" in set_a_tables
    assert set_a_tables["unknown_table"].priority == 999


# Complex validation scenarios
def test_validate_filter_data_types_with_none_values(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(filterBy=[
        FilterModel(field="uid", operator="IN", values=[1, None, 3])
    ])
    _, column_to_table_map = builder._get_explicitly_requested_tables(params)

    errors = builder._validate_filter_data_types(params.filterBy, column_to_table_map)
    assert not errors


def test_validate_filter_data_types_boolean_field(mock_yaml_load):
    builder = SQLBuilder()
    builder.table_configs["newwpnl"].columns.append({
        'name': 'is_active',
        'field_type': 'BOOLEAN',
        'field_aliases': [],
        'supported_operators': ['EQUAL']
    })

    params = GetDataParams(filterBy=[
        FilterModel(field="is_active", operator="EQUAL", values=True)
    ])
    _, column_to_table_map = builder._get_explicitly_requested_tables(params)

    errors = builder._validate_filter_data_types(params.filterBy, column_to_table_map)
    assert not errors

def test_get_count_from_results_estimate_no_pagination(mock_yaml_load):
    builder = SQLBuilder(count_strategy="estimate")
    count_result = [{"estimated_count": -1}]
    main_results = [{"row": i} for i in range(15)]
    params = GetDataParams()

    count = builder.get_count_from_results(count_result, main_results, params)
    assert count == 15


def test_build_query_pagination_edge_cases(mock_yaml_load):
    builder = SQLBuilder()

    params = GetDataParams(groupBy=["uidtype"], page=2)
    main_query, _, _, _ = builder.build_query(params)
    assert "LIMIT" in main_query

    params = GetDataParams(groupBy=["uidtype"], page_size=10)
    main_query, _, _, _ = builder.build_query(params)
    assert "LIMIT" in main_query


# Complex WHERE clause scenarios
def test_build_where_clause_empty_filters(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["uidtype"], filterBy=[])

    main_query, _, _, _ = builder.build_query(params)
    assert "WHERE" not in main_query

# SELECT clause edge cases
def test_build_select_clause_distinct_with_measures(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        measures=[MeasureModel(field="newpnl", function="SUM")],
        groupBy=["uidtype"],
        distinct=True
    )
    main_query, _, _, _ = builder.build_query(params)

    assert "SUM(newpnl)" in main_query
    assert "DISTINCT" not in main_query or "SELECT DISTINCT" not in main_query


def test_build_select_clause_table_prefixed_columns(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["newwpnl.uidtype", "users.name"])

    main_query, _, _, _ = builder.build_query(params)
    assert "SELECT uidtype, name" in main_query or "uidtype" in main_query


# GROUP BY edge cases
def test_build_group_by_clause_no_aggregates(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(groupBy=["uidtype"])

    main_query, _, _, _ = builder.build_query(params)
    assert "GROUP BY" not in main_query


def test_build_group_by_clause_duplicate_fields(mock_yaml_load):
    builder = SQLBuilder()
    params = GetDataParams(
        measures=[MeasureModel(field="newpnl", function="SUM")],
        groupBy=["uidtype", "uidtype"]  # duplicate
    )
    main_query, _, _, _ = builder.build_query(params)

    assert "GROUP BY" in main_query


# Configuration parsing edge cases
def test_parse_table_configs_missing_schema_name(mock_yaml_load):
    builder = SQLBuilder()
    config_data = {
        "SCHEMAS": {
            "test_table": {
                "priority": 1,
                "schema_fields": {"col1": {"field_type": "VARCHAR"}}
            }
        }
    }

    builder._parse_table_configs(config_data)
    assert "test_table" not in builder.table_configs

# Error handling and edge cases
def test_build_distinct_values_query_mixed_restricted_unrestricted(mock_yaml_load):
    builder = SQLBuilder()
    queries = builder.build_distinct_values_query(["uidtype", "uid", "businessdate"])

    assert len(queries) == 3
    unrestricted_queries = [q for q in queries if q[2] is not None]
    restricted_queries = [q for q in queries if q[2] is None]

    assert len(unrestricted_queries) == 2
    assert len(restricted_queries) == 1


def test_construct_final_query_all_parts(mock_yaml_load):
    builder = SQLBuilder()
    builder.query_parts = {
        'select': ['col1', 'col2'],
        'from': 'table1',
        'joins': ['LEFT JOIN table2 ON table1.id = table2.id'],
        'where': ['col1 = ?'],
        'group_by': ['col1'],
        'order_by': 'ORDER BY col1',
        'limit': '10',
        'offset': '5'
    }

    query = builder._construct_final_query()

    assert 'SELECT col1, col2' in query
    assert 'FROM table1' in query
    assert 'LEFT JOIN table2' in query
    assert 'WHERE col1 = ?' in query
    assert 'GROUP BY col1' in query
    assert 'ORDER BY col1' in query
    assert 'LIMIT 10' in query
    assert 'OFFSET 5' in query


def test_construct_final_query_minimal_parts(mock_yaml_load):
    builder = SQLBuilder()
    builder.query_parts = {
        'select': ['*'],
        'from': 'table1',
        'joins': [],
        'where': [],
        'group_by': [],
        'order_by': '',
    }

    query = builder._construct_final_query()

    assert 'SELECT *' in query
    assert 'FROM table1' in query
    assert 'JOIN' not in query
    assert 'WHERE' not in query
    assert 'GROUP BY' not in query
    assert 'ORDER BY' not in query


# Performance and memory tests
def test_reset_clears_all_state(mock_yaml_load):
    builder = SQLBuilder()

    # Set all possible state
    builder.query_parts = {
        'select': ['test'],
        'from': 'test',
        'joins': ['test'],
        'where': ['test'],
        'group_by': ['test'],
        'order_by': 'test',
        'limit': 'test',
        'offset': 'test'
    }
    builder.parameters = [1, 2, 3]

    builder._reset()

    assert builder.query_parts['select'] == []
    assert builder.query_parts['from'] == ''
    assert builder.query_parts['joins'] == []
    assert builder.query_parts['where'] == []
    assert builder.query_parts['group_by'] == []
    assert builder.query_parts['order_by'] == ''
    assert builder.parameters == []
    assert 'limit' not in builder.query_parts or not builder.query_parts.get('limit')
    assert 'offset' not in builder.query_parts or not builder.query_parts.get('offset')