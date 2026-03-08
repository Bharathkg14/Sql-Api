import trino
import trino.auth
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
import logging
import requests
import time
import uuid
from app.settings import settings
from app.correlation_utils import gen_props
import psycopg2

logger = logging.getLogger(__name__)


def execute_query(query: str, params: Optional[List[Any]] = None, is_count_query: bool = False,
                  headers: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Execute a query via API and return results as list of dictionaries"""
    start_time = time.perf_counter()
    try:
        logger.info(f"Starting query execution",
                    extra=gen_props(headers,
                                    endpoint=f"{settings.API_URL}:{settings.API_PORT}/sql",
                                    operation="execute_query",
                                    is_count_query=is_count_query,
                                    has_params=bool(params)))

        if params:
            formatted_query = _format_query_with_params(query, params)
            logger.debug(f"Query formatted with {len(params)} parameters",
                         extra=gen_props(headers, param_count=len(params)))
        else:
            formatted_query = query

        payload = {
            "sql": formatted_query,
            "trace": False,
            "queryOptions": ""
        }

        api_url = f"{settings.API_URL}:{settings.API_PORT}/sql"

        logger.debug(f"Sending API request",
                     extra=gen_props(headers,
                                     api_url=api_url,
                                     payload_size=len(str(payload))))

        response = requests.post(api_url, json=payload, timeout=30)
        response.raise_for_status()

        result_data = response.json()
        execution_time = time.perf_counter() - start_time

        logger.info(f"API request successful",
                    extra=gen_props(headers,
                                    execution_time=execution_time,
                                    response_status=response.status_code,
                                    response_size=len(response.text)))

        if is_count_query:
            if "rows" not in result_data or not result_data["rows"]:
                logger.warning(f"No rows in count query response",
                               extra=gen_props(headers, result_type="empty_count"))
                return [{"count": 0}]

            count_result = [{"count": result_data["rows"][0][0]}]
            logger.info(f"Count query completed",
                        extra=gen_props(headers,
                                        execution_time=execution_time,
                                        count_value=count_result[0]["count"]))
            return count_result

        if "resultTable" not in result_data:
            logger.error(f"Invalid response format - 'resultTable' key missing",
                         extra=gen_props(headers,
                                         execution_time=execution_time,
                                         error_type="InvalidResponseFormat"))
            raise ValueError("Invalid response format from API")

        result_table = result_data["resultTable"]
        column_names = result_table.get("dataSchema", {}).get("columnNames", [])
        rows = result_table.get("rows", [])

        if not column_names:
            logger.warning(f"No column names in API response",
                           extra=gen_props(headers,
                                           execution_time=execution_time,
                                           result_type="empty_columns"))
            return []

        result = [dict(zip(column_names, row)) for row in rows]

        logger.info(f"Query execution completed successfully",
                    extra=gen_props(headers,
                                    execution_time=execution_time,
                                    row_count=len(result),
                                    column_count=len(column_names)))

        return result

    except requests.exceptions.RequestException as e:
        execution_time = time.perf_counter() - start_time
        logger.error(f"API request error - {e}",
                     extra=gen_props(headers,
                                     execution_time=execution_time,
                                     error_type="RequestException",
                                     error_message=str(e)))
        raise
    except ValueError as e:
        execution_time = time.perf_counter() - start_time
        logger.error(f"Response parsing error - {e}",
                     extra=gen_props(headers,
                                     execution_time=execution_time,
                                     error_type="ValueError",
                                     error_message=str(e)))
        raise
    except Exception as e:
        execution_time = time.perf_counter() - start_time
        logger.error(f"Query execution error - {e}",
                     extra=gen_props(headers,
                                     execution_time=execution_time,
                                     error_type="GeneralException",
                                     error_message=str(e)))
        raise