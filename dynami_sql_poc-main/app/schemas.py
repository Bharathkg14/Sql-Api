from pydantic import BaseModel, field_validator
from typing import List, Optional, Any, Dict
from enum import Enum


class AggregationEnum(str, Enum):
    COUNT = "COUNT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


class MeasureModel(BaseModel):
    field: str
    function: str

    @field_validator('function')
    @classmethod
    def valid_function(cls, v):
        valid_functions = {'count', 'sum', 'avg', 'min', 'max'}
        normalized = v.upper()
        if normalized.lower() not in valid_functions:
            raise ValueError(f"Function must be one of {valid_functions}")
        return normalized  # Normalize to uppercase: COUNT, SUM, AVG, MIN, MAX


class FilterModel(BaseModel):
    field: str
    operator: str
    values: Any

    @field_validator('operator')
    @classmethod
    def valid_operator(cls, v):
        valid_operators = {'equal', 'in', 'between', 'inlist'}
        normalized = v.upper()
        if normalized.lower() not in valid_operators:
            raise ValueError(f"Operator must be one of {valid_operators}")
        return normalized  # Normalize to uppercase: EQUAL, IN, BETWEEN, INLIST

    @field_validator('values')
    @classmethod
    def validate_values(cls, v, info):
        operator = info.data.get('operator', '').upper()
        if operator == 'BETWEEN':
            if not isinstance(v, list) or len(v) != 2:
                raise ValueError("BETWEEN requires a list of exactly 2 values")
        elif operator in ['IN', 'INLIST']:
            if not isinstance(v, list) or not v:
                raise ValueError("IN/INLIST requires a non-empty list")
        elif operator == 'EQUAL':
            if v is None or isinstance(v, list):
                raise ValueError("EQUAL requires a single value")
        return v


class SortModel(BaseModel):
    field: str
    order: str = "ASC"

    @field_validator('order')
    @classmethod
    def valid_order(cls, v):
        valid_orders = {'asc', 'desc'}
        normalized = v.upper()
        if normalized.lower() not in valid_orders:
            raise ValueError("Order must be ASC or DESC")
        return normalized  # Normalize to uppercase: ASC, DESC


class GetDataParams(BaseModel):
    measures: Optional[List[MeasureModel]] = []
    groupBy: Optional[List[str]] = []
    filterBy: Optional[List[FilterModel]] = []
    sortBy: Optional[List[SortModel]] = []
    page: Optional[int] = None
    page_size: Optional[int] = None

    @field_validator('page')
    @classmethod
    def page_gte_one(cls, v):
        if v is None or v >= 1:
            return v
        raise ValueError("Page must be greater than or equal to 1")

    @field_validator('page_size')
    @classmethod
    def page_size_gte_one(cls, v):
        if v is None or v >= 1:
            return v
        raise ValueError("Page size must be greater than or equal to 1")

    @field_validator('measures')
    @classmethod
    def measures_check(cls, v):
        return v or []

    @field_validator('filterBy')
    @classmethod
    def filterBy_check(cls, v):
        return v or []

    @field_validator('sortBy')
    @classmethod
    def sortBy_check(cls, v):
        return v or []

    def is_aggregated(self) -> bool:
        """Check if the request requires aggregation"""
        return bool(self.measures)

    def is_distinct_only(self) -> bool:
        """Check if the request is for distinct groupBy values only"""
        return bool(self.groupBy) and not self.measures

    def get_all_columns(self) -> List[str]:
        """Get all columns referenced in the request"""
        columns = []

        # Add groupBy columns
        columns.extend(self.groupBy or [])

        # Add measure fields
        if self.measures:
            columns.extend([measure.field for measure in self.measures])

        # Add filter fields
        if self.filterBy:
            columns.extend([filter_obj.field for filter_obj in self.filterBy])

        # Add sort fields
        if self.sortBy:
            columns.extend([sort_obj.field for sort_obj in self.sortBy])

        return list(set(columns))  # Remove duplicates

class ColumnMetadata(BaseModel):
    field: str
    type: str

class QueryResponse(BaseModel):
    data: List[Any]
    page: int
    page_size: int
    total_count: int = 0
    query: str
    query_id: str
    columns: Optional[List[ColumnMetadata]] = None


# Legacy support - FilterCondition for backward compatibility
class FilterCondition(BaseModel):
    field: str
    operator: str
    values: Any

    @field_validator('operator')
    @classmethod
    def valid_operator(cls, v):
        valid_operators = {'equal', 'in', 'between'}
        normalized = v.upper()
        if normalized.lower() not in valid_operators:
            raise ValueError(f"Operator must be one of {valid_operators}")
        return normalized

    @field_validator('values')
    @classmethod
    def validate_values(cls, v, info):
        operator = info.data.get('operator', '').upper()
        if operator == 'BETWEEN':
            if not isinstance(v, list) or len(v) != 2:
                raise ValueError("BETWEEN requires a list of exactly 2 values")
        elif operator == 'IN':
            if not isinstance(v, list) or not v:
                raise ValueError("IN requires a non-empty list")
        elif operator == 'EQUAL':
            if v is None or isinstance(v, list):
                raise ValueError("EQUAL requires a single value")
        return v

class GetAttributesRequest(BaseModel):
    columns: List[str]
    filterBy: Optional[List[FilterModel]] = None

class AttributeFieldData(BaseModel):
    field: str
    type: str
    values: List[Any]

class GetAttributesResponse(BaseModel):
    query_id: str
    query : str
    data: List[AttributeFieldData]