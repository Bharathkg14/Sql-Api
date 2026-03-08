import fastapi.testclient
from unittest.mock import patch, MagicMock
import uuid

from app.exception import ValidationError
from main import app

client = fastapi.testclient.TestClient(app)
from app.sql_builder import TableConfig

def test_get_data_success(mock_yaml_load, mock_env):
    with patch("app.routes.SQLBuilder") as mock_builder, \
         patch("app.routes.execute_query") as mock_execute:
        mock_builder_instance = mock_builder.return_value
        # Mock the build_query method
        mock_builder_instance.build_query.return_value = (
            "SELECT uidtype, businessdate, SUM(newpnl) AS sum_newpnl FROM newwpnl WHERE businessdate = ? GROUP BY uidtype, businessdate ORDER BY newpnl DESC LIMIT 10",
            [20230101],
            "SELECT COUNT(*) FROM newwpnl WHERE businessdate = ?",
            [20230101]
        )
        # Mock the _get_explicitly_requested_tables method
        mock_builder_instance._get_explicitly_requested_tables.return_value = (
            ["newwpnl"],  # tables
            {
                "uidtype": TableConfig(
                    name="newwpnl",
                    priority=1,
                    columns=[{"name": "uidtype", "type": "INTEGER"}]
                )
            }  # column_to_table_map
        )
        # Mock the _get_column_data_type method
        mock_builder_instance._get_column_data_type.return_value = "INTEGER"
        # Mock execute_query to return count and data results
        mock_execute.side_effect = [[{"count": 1}], [{"uidtype": "value1", "sum_newpnl": 100.0}]]

        response = client.post("/rates/risk/get-data", json={
            "measures": [{"field": "newpnl", "function": "SUM"}],
            "groupBy": ["uidtype"],
            "filterBy": [{"field": "businessdate", "operator": "EQUAL", "values": 20230101}],
            "sortBy": [{"field": "newpnl", "order": "DESC"}],
            "page": 1,
            "page_size": 10
        })
        assert response.status_code == 200
        assert response.json()["total_count"] == 1
        assert response.json()["data"] == [{"uidtype": "value1", "sum_newpnl": 100.0}]
        assert response.json()["columns"] is None

def test_get_data_validation_error(mock_yaml_load, mock_env):
    with patch("app.routes.SQLBuilder") as mock_builder:
        mock_builder_instance = mock_builder.return_value
        mock_builder_instance.build_query.side_effect = ValidationError([{"field": "measures", "message": "Invalid column 'invalid'"}])
        response = client.post("/rates/risk/get-data", json={"measures": [{"field": "invalid", "function": "SUM"}]})
        assert response.status_code == 400
        assert "errors" in response.json()["detail"]
        assert response.json()["detail"]["errors"][0]["message"] == "Invalid column 'invalid'"
        assert response.json()["detail"]["errors"][0]["field"] == "measures"

# def test_get_data_invalid_json(mock_yaml_load, mock_env):
#     response = client.post("/rates/risk/get-data", json={"invalid_field": "value"})
#     assert response.status_code == 422  # FastAPI validation error
#     assert "detail" in response.json()

def test_get_data_server_error(mock_yaml_load, mock_env):
    with patch("app.routes.SQLBuilder") as mock_builder, \
         patch("app.routes.execute_query") as mock_execute:
        mock_builder_instance = mock_builder.return_value
        mock_builder_instance.build_query.return_value = ("SELECT *", [], "SELECT COUNT(*)", [])
        mock_execute.side_effect = Exception("Database error")
        response = client.post("/rates/risk/get-data", json={"groupBy": ["uidtype"]})
        assert response.status_code == 500
        assert "Database error" in response.json()["detail"]["errors"][0]["message"]


def test_get_attributes_success(mock_yaml_load, mock_env):
    with patch("app.routes.SQLBuilder") as mock_builder, \
            patch("app.routes.execute_query") as mock_execute:
        # Mock SQLBuilder instance and its methods
        mock_builder_instance = mock_builder.return_value
        mock_builder_instance._validate_columns.return_value = []  # No column validation errors
        mock_builder_instance._validate_filter_data_types.return_value = []  # No filter validation errors

        # Create a mock table config object with restricted_attributes
        mock_table_config = MagicMock()
        mock_table_config.restricted_attributes = []  # Empty list for no restricted columns

        # Mock _get_explicitly_requested_tables to return table config object
        mock_builder_instance._get_explicitly_requested_tables.return_value = (
            ["newwpnl"],  # Tables
            {"uidtype": mock_table_config}  # Column-to-table mapping with mock object
        )
        mock_builder_instance._get_column_data_type.return_value = "VARCHAR"
        mock_builder_instance.build_query.return_value = (
            "SELECT DISTINCT uidtype FROM newwpnl WHERE uidtype IS NOT NULL",
            [],  # Main query parameters
            "SELECT COUNT(DISTINCT uidtype) FROM newwpnl WHERE uidtype IS NOT NULL",
            []  # Count query parameters
        )

        mock_execute.return_value = [{"uidtype": "value1"}, {"uidtype": "value2"}]

        response = client.post("/rates/risk/get-attributes", json={"columns": ["uidtype"]})

        assert response.status_code == 200, f"Expected status 200, got {response.status_code}"
        response_json = response.json()

        assert "query_id" in response_json, "Response must contain query_id"
        assert response_json["query"] == "SELECT DISTINCT uidtype FROM newwpnl WHERE uidtype IS NOT NULL"
        assert response_json["data"] == [
            {
                "field": "uidtype",
                "type": "VARCHAR",
                "values": ["value1", "value2"]
            }
        ]
        assert len(response_json["data"]) == 1, "Expected 1 field in data"
        assert len(response_json["data"][0]["values"]) == 2, "Expected 2 distinct values"

def test_get_attributes_validation_error(mock_yaml_load, mock_env):
    with patch("app.routes.SQLBuilder") as mock_builder:
        mock_builder_instance = mock_builder.return_value
        mock_builder_instance._validate_columns.return_value = [{"field": "columns", "message": "Invalid column 'invalid'"}]
        mock_builder_instance.build_distinct_values_query.side_effect = ValidationError([{"field": "columns", "message": "Invalid column 'invalid'"}])
        response = client.post("/rates/risk/get-attributes", json={"columns": ["invalid"]})
        assert response.status_code == 400
        assert "errors" in response.json()["detail"]
        assert response.json()["detail"]["errors"][0]["message"] == "Invalid column 'invalid'"
        assert "query_id" in response.json()["detail"]

def test_get_attributes_invalid_json(mock_yaml_load, mock_env):
    response = client.post("/rates/risk/get-attributes", json={"invalid_field": "value"})
    assert response.status_code == 422
    assert "detail" in response.json()