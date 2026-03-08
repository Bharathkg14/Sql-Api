import pytest
from unittest.mock import patch, MagicMock
from app.database import execute_query
import requests

@pytest.fixture
def mock_settings():
    with patch("app.database.settings") as mock_settings:
        mock_settings.API_URL = "http://fake-api"
        mock_settings.API_PORT = "8080"
        yield mock_settings

@pytest.fixture
def mock_session():
    with patch("requests.Session") as mock_session_class:
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_session.post.return_value.json.return_value = {
            "resultTable": {
                "dataSchema": {"columnNames": ["col1"]},
                "rows": [["value1"]]
            }
        }
        mock_session.post.return_value.raise_for_status = lambda: None
        yield mock_session

def test_execute_query_success(mock_session, mock_settings):
    result = execute_query("SELECT col1 FROM fake_table")
    assert result == [{"col1": "value1"}]
    mock_session.post.assert_called_once_with(
        "http://fake-api:8080/sql",
        json={"sql": "SELECT col1 FROM fake_table", "trace": False, "queryOptions": ""},
        timeout=30
    )

def test_execute_query_count(mock_session, mock_settings):
    mock_session.post.return_value.json.return_value = {"rows": [[5]]}
    mock_session.post.return_value.raise_for_status = lambda: None
    result = execute_query("SELECT COUNT(*) FROM fake_table", is_count_query=True)
    assert result == [{"count": 5}]

def test_execute_query_count_empty(mock_session, mock_settings):
    mock_session.post.return_value.json.return_value = {"rows": []}
    mock_session.post.return_value.raise_for_status = lambda: None
    result = execute_query("SELECT COUNT(*) FROM fake_table", is_count_query=True)
    assert result == [{"count": 0}]

def test_execute_query_request_error(mock_session, mock_settings):
    mock_session.post.side_effect = requests.exceptions.RequestException("API error")
    with pytest.raises(requests.exceptions.RequestException):
        execute_query("SELECT col1 FROM fake_table")

def test_execute_query_invalid_response(mock_session, mock_settings):
    mock_session.post.return_value.json.return_value = {}  # Missing resultTable
    mock_session.post.return_value.raise_for_status = lambda: None
    with pytest.raises(ValueError, match="Invalid response format from API"):
        execute_query("SELECT col1 FROM fake_table")

@patch("app.database._format_query_with_params")
def test_execute_query_with_params(mock_format_query, mock_session, mock_settings):
    mock_format_query.return_value = "SELECT col1 FROM fake_table WHERE id = %s"
    mock_session.post.return_value.json.return_value = {
        "resultTable": {
            "dataSchema": {"columnNames": ["col1"]},
            "rows": [["value1"]]
        }
    }
    mock_session.post.return_value.raise_for_status = lambda: None
    result = execute_query("SELECT col1 FROM fake_table WHERE id = %s", params=[42])
    assert result == [{"col1": "value1"}]
    mock_format_query.assert_called_once_with("SELECT col1 FROM fake_table WHERE id = %s", [42])