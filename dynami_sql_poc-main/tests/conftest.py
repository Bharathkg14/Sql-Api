from unittest.mock import patch, mock_open

import pytest

from app.schemas import GetDataParams, FilterModel, MeasureModel, SortModel

# Mock YAML configuration for testing
SAMPLE_YAML_CONFIG = """
SCHEMAS:
  newwpnl:
    schema_name: "newwpnl"
    priority: 1
    mandatory_fields: ["uidtype", "businessdate"]
    restricted_attributes: ["uid"]
    aggregation:
      - field: "newpnl"
        function: "SUM"
        alias: "total_newpnl"
    schema_fields:
      uid:
        field_type: "INTEGER"
        field_aliases: ["user_id"]
        supported_operators: ["EQUAL", "IN"]
      uidtype:
        field_type: "VARCHAR"
        field_aliases: ["user_type"]
        supported_operators: ["EQUAL", "IN"]
      businessdate:
        field_type: "INTEGER"
        field_aliases: ["bdate", "date"]
        supported_operators: ["EQUAL", "BETWEEN", "IN"]
      newpnl:
        field_type: "DOUBLE PRECISION"
        field_aliases: ["profit_loss", "pnl"]
        supported_operators: ["SUM", "AVG", "COUNT"]
    relations:
      - name: "users"
        type: "LEFT"
        joinColumns:
          - source: "uid"
            target: "id"
  users:
    schema_name: "users"
    priority: 2
    mandatory_fields: ["id"]
    schema_fields:
      id:
        field_type: "INTEGER"
        field_aliases: []
        supported_operators: ["EQUAL", "IN"]
      name:
        field_type: "VARCHAR"
        field_aliases: ["username"]
        supported_operators: ["EQUAL", "IN"]
    relations:
      - name: "profile"
        type: "LEFT"
        joinColumns:
          - name: "id"
  profile:
    schema_name: "profile"
    priority: 3
    schema_fields:
      id:
        field_type: "INTEGER"
        field_aliases: []
        supported_operators: ["EQUAL", "IN"]
      email:
        field_type: "VARCHAR"
        field_aliases: []
        supported_operators: ["EQUAL", "IN"]
"""

@pytest.fixture
def sample_get_data_params():
    return GetDataParams(
        measures=[MeasureModel(field="newpnl", function="SUM")],
        groupBy=["uidtype"],
        filterBy=[FilterModel(field="businessdate", operator="EQUAL", values=20230101)],
        sortBy=[SortModel(field="newpnl", order="DESC")],
        page=1,
        page_size=10
    )

@pytest.fixture
def mock_yaml_load():
    with patch('builtins.open', mock_open(read_data=SAMPLE_YAML_CONFIG)), \
            patch('os.path.exists', return_value=True):
        yield

@pytest.fixture
def sample_table_config_yaml():
    return SAMPLE_YAML_CONFIG

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("API_URL", "http://api")
    monkeypatch.setenv("API_PORT", "8080")
    yield