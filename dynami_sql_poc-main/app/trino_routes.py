import uuid

from fastapi import APIRouter, HTTPException, status
from app.schemas import GetDataParams, QueryResponse
from app.sql_builder import SQLBuilder, ValidationError
from app.database import execute_query
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/rates/risk/{datasource}/get-data", response_model=QueryResponse)
async def execute_dynamic_query(datasource: str, params: GetDataParams):
    query_id = str(uuid.uuid4())
    try:
        sql_builder = SQLBuilder()
        main_query, main_params, count_query, count_params = sql_builder.build_query(params)

        logger.info(f"Executing main query: {main_query}")
        logger.info(f"Main parameters: {main_params}")
        if count_query:
            logger.info(f"Executing count query: {count_query}")
            logger.info(f"Count parameters: {count_params}")

        total_count = 0
        if count_query:
            count_result = execute_query(count_query, count_params, datasource)
            if count_result and len(count_result) > 0:
                total_count = count_result[0]["count"]

        results = execute_query(main_query, main_params, datasource)

        response = QueryResponse(
            data=results,
            page=params.page,
            page_size=params.page_size,
            total_count=total_count,
            query=main_query,
            query_id=query_id
        )

        return response
    except ValidationError as e:
        logger.error(f"Validation error: {e.errors}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": e.errors}
        )
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"errors": [{"message": f"Internal server error occurred while executing query: {str(e)}"}]}
        )