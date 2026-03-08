from fastapi import APIRouter, HTTPException, status, Request
from app.schemas import GetDataParams, QueryResponse, GetAttributesRequest, GetAttributesResponse, ColumnMetadata, AttributeFieldData
from app.sql_builder import SQLBuilder, ValidationError
from app.database import execute_query
from app.utils import get_correlation_id_and_soeid, gen_props, gen_headers
import logging
import uuid
import time

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/rates/risk/get-data", response_model=QueryResponse)
async def execute_dynamic_query(params: GetDataParams, request: Request):
    headers = gen_headers(request, endpoint=str(request.url))
    start_time = time.perf_counter()
    query_id = headers.get("correlation-id")

    try:
        logger.info(f"Starting dynamic query execution for query_id: {query_id}",
                    extra=gen_props(headers,
                                    query_id=query_id,
                                    operation="get-data",
                                    params=params.dict()))

        sql_builder = SQLBuilder()
        main_query, main_params, count_query, count_params = sql_builder.build_query(params)

        total_count = 0
        if count_query:
            count_result = execute_query(count_query, count_params)
            total_count = count_result[0]["count"] if count_result else 0

        results = execute_query(main_query, main_params)

        # Include column metadata if no measures are provided and groupBy exists
        column_metadata = None
        if params.groupBy and not params.measures:
            _, column_to_table_map = sql_builder._get_explicitly_requested_tables(params)
            column_metadata = [
                ColumnMetadata(
                    field=col,
                    type=sql_builder._get_column_data_type(col, column_to_table_map) or "UNKNOWN"
                ) for col in params.groupBy
            ]

        execution_time = time.perf_counter() - start_time

        logger.info(f"Query executed successfully for query_id: {query_id}",
                    extra=gen_props(headers,
                                    query_id=query_id,
                                    execution_time=execution_time,
                                    result_count=len(results),
                                    total_count=total_count))

        return QueryResponse(
            query_id=query_id,
            data=results,
            page=params.page,
            page_size=params.page_size,
            total_count=total_count,
            query=main_query,
            columns=column_metadata
        )

    except ValidationError as e:
        execution_time = time.perf_counter() - start_time
        logger.error(f"Query ID: {query_id} - Validation error: {e.errors}",
                     extra=gen_props(headers,
                                     query_id=query_id,
                                     execution_time=execution_time,
                                     error_type="ValidationError"))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"query_id": query_id, "errors": e.errors}
        )
    except Exception as e:
        execution_time = time.perf_counter() - start_time
        logger.error(f"Query ID: {query_id} - Query execution error: {e}",
                     extra=gen_props(headers,
                                     query_id=query_id,
                                     execution_time=execution_time,
                                     error_type="InternalServerError",
                                     error_message=str(e)))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"query_id": query_id, "errors": [{"message": f"Internal server error: {str(e)}"}]}
        )
@router.post("/rates/risk/get-attributes", response_model=GetAttributesResponse)
async def get_attributes(params: GetAttributesRequest, request: Request):
    headers = gen_headers(request,endpoint=str(request.url))
    start_time = time.perf_counter()
    query_id = headers.get("correlation-id")

    try:
        logger.info(f"Starting get attributes for query_id: {query_id}",
                    extra=gen_props(headers,
                                    query_id=query_id,
                                    operation="get-attributes",
                                    columns=params.columns))

        sql_builder = SQLBuilder()

        # Validate columns and filters
        all_errors = sql_builder._validate_columns(params.columns)
        if params.filterBy:
            _, column_to_table_map = sql_builder._get_explicitly_requested_tables(
                GetDataParams(groupBy=params.columns, filterBy=params.filterBy))
            filter_errors = sql_builder._validate_filter_data_types(params.filterBy, column_to_table_map)
            all_errors.extend(filter_errors)
        if all_errors:
            raise ValidationError(all_errors)

        # Use build_query to get distinct combinations
        query_params = GetDataParams(
            groupBy=params.columns,
            filterBy=params.filterBy or [],
        )
        _, column_to_table_map = sql_builder._get_explicitly_requested_tables(query_params)

        # Check for restricted columns and filter them out
        is_restricted = False
        restricted_columns = []
        for column in params.columns:
            table_config = column_to_table_map.get(column)
            if table_config and column in table_config.restricted_attributes:
                is_restricted = True
                restricted_columns.append(column)

        # Remove restricted columns from groupBy
        if is_restricted:
            query_params.groupBy = [col for col in query_params.groupBy if col not in restricted_columns]

        main_query, main_params, count_query, count_params = sql_builder.build_query(query_params)

        # Execute query for distinct combinations
        results = execute_query(main_query, main_params)

        execution_time = time.perf_counter() - start_time

        logger.info(f"Attributes retrieved successfully for query_id: {query_id}",
                    extra=gen_props(headers,
                                    query_id=query_id,
                                    execution_time=execution_time,
                                    attributes_count=len(results)))

        # Transform results to new format: group by field and extract values
        transformed_data = []
        for col in params.columns:
            # Skip restricted columns that were filtered out from the query
            if col in restricted_columns:
                continue
                
            col_type = sql_builder._get_column_data_type(col, column_to_table_map) or "UNKNOWN"
            # Extract all values for this column from results
            col_values = [row[col] for row in results if col in row]
            
            transformed_data.append(
                AttributeFieldData(
                    field=col,
                    type=col_type,
                    values=col_values
                )
            )

        return GetAttributesResponse(
            query_id=query_id,
            data=transformed_data,
            query=main_query
        )

    except ValidationError as e:
        execution_time = time.perf_counter() - start_time
        logger.error(f"Query ID: {query_id} - Validation error: {e.errors}",
                     extra=gen_props(headers,
                                     query_id=query_id,
                                     execution_time=execution_time,
                                     error_type="ValidationError"))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"query_id": query_id, "errors": e.errors}
        )
    except Exception as e:
        execution_time = time.perf_counter() - start_time
        logger.error(f"Query ID: {query_id} - Query execution error: {e}",
                     extra=gen_props(headers,
                                     query_id=query_id,
                                     execution_time=execution_time,
                                     error_type="InternalServerError",
                                     error_message=str(e)))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"query_id": query_id, "errors": [{"message": f"Internal server error: {str(e)}"}]}
        )