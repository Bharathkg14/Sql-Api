import trino
import trino.auth
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
import logging
from app.settings import settings

logger = logging.getLogger(__name__)

@contextmanager
def get_db_connection(datasource):
    """Context manager for Trino database connections"""
    conn = None
    try:
        conn = trino.dbapi.connect(
            host="",
            port=8788,
            http_scheme="https",
            auth=trino.auth.BasicAuthentication(
                username="",
                password=""
            ),
            catalog=datasource,
            schema="default",
            verify=False
        )
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def execute_query(query: str, params: Optional[List[Any]] = None, datasource: str = 'default') -> List[Dict[str, Any]]:
    """Execute a query and return results as list of dictionaries"""
    try:
        with get_db_connection(datasource) as conn:
            cursor = conn.cursor()

            if params:
                formatted_query = _format_query_with_params(query, params)
                cursor.execute(formatted_query)
            else:
                cursor.execute(query)

            rows = cursor.fetchall()
            columns = [col["name"] for col in cursor._query.columns] if cursor._query.columns else []
            result = [dict(zip(columns, row)) for row in rows]
            # if cursor.description:
            #     columns = [desc[0] for desc in cursor.description]
            #     # Convert rows to dictionaries
            #     result = []
            #     for row in rows:
            #         result.append(dict(zip(columns, row)))
            #     return result
            # else:
            #     return []
            return result
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        raise

def _format_query_with_params(query: str, params: List[Any]) -> str:
    """Format query with parameters for Trino"""
    formatted_query = query
    param_index = 0

    while '?' in formatted_query and param_index < len(params):
        param = params[param_index]
        if isinstance(param, str):
            escaped_param = f"'{param.replace(chr(39), chr(39) + chr(39))}'"
        elif isinstance(param, (int, float)):
            escaped_param = str(param)
        elif isinstance(param, list):
            escaped_items = [f"'{item.replace(chr(39), chr(39) + chr(39))}'" if isinstance(item, str) else str(item) for item in param]
            escaped_param = ','.join(escaped_items)
        else:
            escaped_param = str(param)

        formatted_query = formatted_query.replace('?', escaped_param, 1)
        param_index += 1

    return formatted_query