import os
import yaml
from typing import List, Any, Dict, Tuple, Optional

from app.exception import ValidationError
from app.schemas import GetDataParams, FilterModel, MeasureModel

class TableConfig:
    def __init__(self, name: str, priority: int, columns: List[Dict], relations: List[Dict] = None,
                 mandatory_fields: List[str] = None, aggregations: List[Dict] = None, restricted_attributes: List[str] = None):
        self.name = name
        self.priority = priority
        self.columns = columns or []
        self.relations = relations or []
        self.mandatory_fields = mandatory_fields or []
        self.aggregations = aggregations or []
        self.restricted_attributes = restricted_attributes or []


class JoinRelation:
    def __init__(self, target_table: str, join_type: str, join_columns: List[Dict]):
        self.target_table = target_table
        self.join_type = join_type
        self.join_columns = join_columns


class SQLBuilder:
    def __init__(self, config_path: str = "config/table_config.yaml", count_strategy: str = "simple"):
        self.query_parts = {
            'select': [],
            'from': '',
            'joins': [],
            'where': [],
            'group_by': [],
            'order_by': '',
        }
        self.parameters = []
        self.table_configs = {}
        self.config_path = config_path
        self.count_strategy = count_strategy
        self._load_table_configurations()

    def _load_table_configurations(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as file:
                    config_data = yaml.safe_load(file)
                    self._parse_table_configs(config_data)
            else:
                print(f"Warning: Configuration file {self.config_path} not found. Joins will be disabled.")
        except Exception as e:
            print(f"Error loading configuration: {e}")

    def _parse_table_configs(self, config_data: Dict):
        if 'SCHEMAS' in config_data:
            for schema_name, table_data in config_data['SCHEMAS'].items():
                name = table_data.get('schema_name')
                priority = table_data.get('priority', 999)
                columns = [
                    {'name': field_name,
                     'field_aliases': field_data.get('field_aliases', []),
                     'field_type': field_data.get('field_type'),
                     'supported_operators': field_data.get('supported_operators', [])}
                    for field_name, field_data in table_data.get('schema_fields', {}).items()
                ]
                relations = table_data.get('relations', [])
                mandatory_fields = table_data.get('mandatory_fields', [])
                aggregations = table_data.get('aggregation', [])
                restricted_attributes = table_data.get('restricted_attributes', [])

                if name:
                    config = TableConfig(name, priority, columns, relations, mandatory_fields, aggregations, restricted_attributes)
                    self.table_configs[name] = config

    def _matches_field_name(self, input_name: str, actual_name: str, aliases: List[str]) -> bool:
        """
        Check if input_name matches actual_name or any alias (case-insensitive).
        
        Args:
            input_name: The name to check
            actual_name: The actual field name from config
            aliases: List of aliases for the field
            
        Returns:
            True if input_name matches actual_name or any alias (case-insensitive)
        """
        if input_name.lower() == actual_name.lower():
            return True
        return any(input_name.lower() == alias.lower() for alias in aliases)

    def _resolve_table_column_format(self, table_name: str, col_name: str) -> str:
        """
        Resolve a field name in table.column format to actual field name.
        
        Args:
            table_name: The table name
            col_name: The column name (could be alias or case-variant)
            
        Returns:
            The resolved field name in table.column format, or original if not found
        """
        if table_name not in self.table_configs:
            return f"{table_name}.{col_name}"
        
        table_config = self.table_configs[table_name]
        for col_def in table_config.columns:
            actual_name = col_def.get('name')
            aliases = col_def.get('field_aliases', [])
            
            if self._matches_field_name(col_name, actual_name, aliases):
                return f"{table_name}.{actual_name}"
        
        return f"{table_name}.{col_name}"

    def _resolve_column_from_table_config(self, field_name: str, table_config: TableConfig) -> Optional[str]:
        """
        Resolve a field name by searching in a specific table config.
        
        Args:
            field_name: The field name to resolve
            table_config: The table config to search in
            
        Returns:
            The actual field name if found, None otherwise
        """
        for col_def in table_config.columns:
            actual_name = col_def.get('name')
            aliases = col_def.get('field_aliases', [])
            
            if self._matches_field_name(field_name, actual_name, aliases):
                return actual_name
        return None

    def _resolve_from_column_to_table_map(self, field_name: str, column_to_table_map: Dict[str, TableConfig]) -> Optional[str]:
        """
        Try to resolve field name using column_to_table_map.
        
        Args:
            field_name: The field name to resolve
            column_to_table_map: Mapping of columns to table configs
            
        Returns:
            The actual field name if found, None otherwise
        """
        for key, table_config in column_to_table_map.items():
            if key.lower() != field_name.lower():
                continue
                
            table_name = table_config.name
            if table_name not in self.table_configs:
                continue
                
            resolved = self._resolve_column_from_table_config(
                field_name, self.table_configs[table_name]
            )
            if resolved:
                return resolved
        
        return None

    def _resolve_from_all_tables(self, field_name: str) -> Optional[str]:
        """
        Search all table configs to resolve field name.
        
        Args:
            field_name: The field name to resolve
            
        Returns:
            The actual field name if found, None otherwise
        """
        for table_config in self.table_configs.values():
            resolved = self._resolve_column_from_table_config(field_name, table_config)
            if resolved:
                return resolved
        return None

    def _resolve_column_format(self, field_name: str, column_to_table_map: Dict[str, TableConfig] = None) -> str:
        """
        Resolve a field name in column-only format to actual field name.
        
        Args:
            field_name: The field name to resolve
            column_to_table_map: Optional mapping of columns to table configs
            
        Returns:
            The actual field name if found, original field_name otherwise
        """
        # First try to find using column_to_table_map if provided
        if column_to_table_map:
            resolved = self._resolve_from_column_to_table_map(field_name, column_to_table_map)
            if resolved:
                return resolved
        
        # If column_to_table_map not provided or not found, search all tables
        resolved = self._resolve_from_all_tables(field_name)
        if resolved:
            return resolved
        
        # If not found, return as is (might be a column not in config)
        return field_name

    def _resolve_field_name(self, field_name: str, column_to_table_map: Dict[str, TableConfig] = None) -> str:
        """
        Resolve a field name (which could be an alias or case-variant) to the actual field name.
        Supports both 'table.column' and 'column' formats.
        Case-insensitive matching: 'uidtype' matches 'UidType' and returns 'UidType'.
        
        Args:
            field_name: The field name or alias to resolve (case-insensitive)
            column_to_table_map: Optional mapping of columns to table configs
            
        Returns:
            The actual field name (with correct case from config), in the same format as input
        """
        if '.' in field_name:
            table_name, col_name = field_name.split('.', 1)
            return self._resolve_table_column_format(table_name, col_name)
        else:
            return self._resolve_column_format(field_name, column_to_table_map)

    def _column_exists_in_table_config(self, col_name: str, table_config: TableConfig) -> bool:
        """
        Check if a column exists in a table config (case-insensitive).
        
        Args:
            col_name: The column name to check
            table_config: The table config to search in
            
        Returns:
            True if column exists, False otherwise
        """
        for col_def in table_config.columns:
            actual_name = col_def.get('name')
            aliases = col_def.get('field_aliases', [])
            if self._matches_field_name(col_name, actual_name, aliases):
                return True
        return False

    def _validate_table_column_format(self, column: str, table_name: str, col_name: str) -> Optional[Dict]:
        """
        Validate a column in table.column format.
        
        Args:
            column: The full column string (for error message)
            table_name: The table name
            col_name: The column name
            
        Returns:
            Error dict if validation fails, None otherwise
        """
        if table_name not in self.table_configs:
            return {
                "field": "columns",
                "message": f"Table '{table_name}' in column '{column}' not found in configurations"
            }
        
        table_config = self.table_configs[table_name]
        if not self._column_exists_in_table_config(col_name, table_config):
            return {
                "field": "columns",
                "message": f"Column '{column}' does not exist in table '{table_name}'"
            }
        
        return None

    def _validate_column_only_format(self, column: str, col_name: str) -> Optional[Dict]:
        """
        Validate a column in column-only format.
        
        Args:
            column: The column name
            col_name: The column name (same as column, for consistency)
            
        Returns:
            Error dict if validation fails, None otherwise
        """
        for table_config in self.table_configs.values():
            if self._column_exists_in_table_config(col_name, table_config):
                return None
        
        return {
            "field": "columns",
            "message": f"Column '{column}' not found in any table"
        }

    def _validate_columns(self, columns: List[str]) -> List[Dict]:
        errors = []

        for column in columns:
            if '.' in column:
                table_name, col_name = column.split('.', 1)
                error = self._validate_table_column_format(column, table_name, col_name)
                if error:
                    errors.append(error)
            else:
                error = self._validate_column_only_format(column, column)
                if error:
                    errors.append(error)

        return errors

    def _get_column_data_type(self, column: str, column_to_table_map: Dict[str, TableConfig]) -> str:
        table_name = None
        col_name = column

        if '.' in column:
            table_name, col_name = column.split('.', 1)
        else:
            # Case-insensitive lookup in column_to_table_map
            for key, table_config in column_to_table_map.items():
                if key.lower() == col_name.lower():
                    table_name = table_config.name
                    break

        if table_name and table_name in self.table_configs:
            table_config = self.table_configs[table_name]
            for col_def in table_config.columns:
                actual_name = col_def.get('name')
                aliases = col_def.get('field_aliases', [])
                # Case-insensitive matching
                if (col_name.lower() == actual_name.lower() or 
                    any(col_name.lower() == alias.lower() for alias in aliases)):
                    return col_def.get('field_type')
        return None

    def _get_supported_operators(self, column: str, column_to_table_map: Dict[str, TableConfig]) -> List[str]:
        table_name = None
        col_name = column

        # Case-insensitive lookup in column_to_table_map
        for key, table_config in column_to_table_map.items():
            if key.lower() == col_name.lower():
                table_name = table_config.name
                break

        if table_name and table_name in self.table_configs:
            table_config = self.table_configs[table_name]
            for col_def in table_config.columns:
                actual_name = col_def.get('name')
                aliases = col_def.get('field_aliases', [])
                # Case-insensitive matching
                if (col_name.lower() == actual_name.lower() or 
                    any(col_name.lower() == alias.lower() for alias in aliases)):
                    return col_def.get('supported_operators', [])
        return []

    def _validate_filter_data_types(self, filters: List[FilterModel], column_to_table_map: Dict[str, TableConfig]) -> \
            List[Dict]:
        errors = []
        type_mapping = {
            'varchar': (str,),
            'integer': (int,),
            'double precision': (float, int),
            'boolean': (bool,),
        }

        for i, filter_obj in enumerate(filters):
            if not isinstance(filter_obj, FilterModel):
                errors.append({
                    "field": "filters",
                    "message": f"Filter at index {i} is not a valid FilterModel: {filter_obj}"
                })
                continue

            column = filter_obj.field
            operator = filter_obj.operator.upper()
            values = filter_obj.values

            expected_type = self._get_column_data_type(column, column_to_table_map)
            if not expected_type:
                continue

            expected_python_types = type_mapping.get(expected_type.lower(), ())
            if not expected_python_types:
                continue

            if operator == 'BETWEEN':
                if not isinstance(values, list) or len(values) != 2:
                    errors.append({
                        "field": "filters",
                        "message": f"Invalid BETWEEN range for column '{column}' at index {i}: must be a list of two values"
                    })
                    continue
                for val in values:
                    if val is None:
                        continue
                    if not isinstance(val, expected_python_types):
                        errors.append({
                            "field": "filters",
                            "message": f"Invalid data type for column '{column}' in BETWEEN range at index {i}",
                            "expected": expected_type,
                            "actual": type(val).__name__,
                            "value": str(val)
                        })
            elif operator in ['IN', 'INLIST']:
                if not isinstance(values, list) or not values:
                    errors.append({
                        "field": "filters",
                        "message": f"Invalid IN/INLIST values for column '{column}' at index {i}: must be a non-empty list"
                    })
                    continue
                for val in values:
                    if val is None:
                        continue
                    if not isinstance(val, expected_python_types):
                        errors.append({
                            "field": "filters",
                            "message": f"Invalid data type for column '{column}' in IN/INLIST at index {i}",
                            "expected": expected_type,
                            "actual": type(val).__name__,
                            "value": str(val)
                        })
            elif operator == 'EQUAL':
                if values is None:
                    continue
                if not isinstance(values, expected_python_types):
                    errors.append({
                        "field": "filters",
                        "message": f"Invalid data type for column '{column}' with EQUAL operator at index {i}: must be a single value",
                        "expected": expected_type,
                        "actual": type(values).__name__,
                        "value": str(values)
                    })
            else:
                errors.append({
                    "field": "filters",
                    "message": f"Unsupported operator '{operator}' for column '{column}' at index {i}. Supported operators: EQUAL, IN, INLIST, BETWEEN"
                })

        return errors

    def _validate_measures(self, measures: List[MeasureModel]) -> List[Dict]:
        errors = []
        valid_functions = {'SUM', 'COUNT', 'AVG', 'MAX', 'MIN'}

        # Get column-to-table mapping for measures
        _, column_to_table_map = self._get_explicitly_requested_tables(GetDataParams(measures=measures))

        for i, measure in enumerate(measures):
            if not isinstance(measure, MeasureModel):
                errors.append({
                    "field": "measures",
                    "message": f"Measure at index {i} is not a valid MeasureModel: {measure}"
                })
                continue

            column_errors = self._validate_columns([measure.field])
            if column_errors:
                errors.extend([
                    {**error, "field": "measures", "message": error["message"].replace("columns", "measures")}
                    for error in column_errors
                ])

            function = measure.function.upper()
            if function not in valid_functions:
                errors.append({
                    "field": "measures",
                    "message": f"Invalid aggregation function '{measure.function}' for field '{measure.field}' at index {i}. Valid functions: {', '.join(valid_functions)}"
                })
                continue

            # Validate against supported_operators in table config
            supported_operators = self._get_supported_operators(measure.field, column_to_table_map)
            if supported_operators and function not in supported_operators:
                errors.append({
                    "field": "measures",
                    "message": f"Aggregation function '{function}' is not supported for field '{measure.field}' at index {i}. Supported functions: {', '.join(supported_operators)}"
                })

        return errors

    def _get_relations_for_table(self, table_config: TableConfig) -> List[Dict]:
        return table_config.relations

    def _get_reverse_relations_for_table(self, table_config: TableConfig) -> List[Dict]:
        reverse_relations = []

        for other_name, other_config in self.table_configs.items():
            if other_name == table_config.name:
                continue

            for relation in other_config.relations:
                relation_target_name = relation.get('name')

                if relation_target_name == table_config.name:
                    reverse_relation = {
                        'source_table': other_config.name,
                        'target_table': table_config.name,
                        'type': relation.get('type', 'LEFT'),
                        'joinColumns': relation.get('joinColumns', []),
                        'original_relation': relation
                    }
                    reverse_relations.append(reverse_relation)

        return reverse_relations

    def _collect_filtered_fields(self, params: GetDataParams, column_to_table_map: Dict[str, TableConfig]) -> set:
        """
        Collect all filtered field names (resolved to actual names).
        
        Args:
            params: The request parameters
            column_to_table_map: Mapping of columns to table configs
            
        Returns:
            Set of resolved field names
        """
        filtered_fields = {self._resolve_field_name(f.field, column_to_table_map) for f in (params.filterBy or [])}
        
        # Also check if any aliases match mandatory fields
        for f in (params.filterBy or []):
            resolved = self._resolve_field_name(f.field, column_to_table_map)
            if '.' in resolved:
                _, col_name = resolved.split('.', 1)
                filtered_fields.add(col_name)
            else:
                filtered_fields.add(resolved)
        
        return filtered_fields

    def _is_mandatory_field_found(self, mand_field: str, filtered_fields: set) -> bool:
        """
        Check if a mandatory field is found in filtered fields (case-insensitive).
        
        Args:
            mand_field: The mandatory field name
            filtered_fields: Set of filtered field names
            
        Returns:
            True if mandatory field is found, False otherwise
        """
        # Case-insensitive check in filtered_fields
        if any(f.lower() == mand_field.lower() for f in filtered_fields):
            return True
        
        # Check if any filter field is an alias or case-variant for this mandatory field
        for table_config in self.table_configs.values():
            for col_def in table_config.columns:
                actual_name = col_def.get('name')
                aliases = col_def.get('field_aliases', [])
                
                # Check if mandatory field matches this column definition (case-insensitive)
                if not self._matches_field_name(mand_field, actual_name, aliases):
                    continue
                
                # Check if any filtered field matches (case-insensitive)
                for filtered_field in filtered_fields:
                    if self._matches_field_name(filtered_field, actual_name, aliases):
                        return True
        
        return False

    def _validate_mandatory_filters(self, params: GetDataParams, used_tables: Dict[str, TableConfig], 
                                    column_to_table_map: Dict[str, TableConfig]) -> List[Dict]:
        """
        Validate that all mandatory filters are present.
        
        Args:
            params: The request parameters
            used_tables: Tables used in the query
            column_to_table_map: Mapping of columns to table configs
            
        Returns:
            List of validation errors
        """
        errors = []
        filtered_fields = self._collect_filtered_fields(params, column_to_table_map)
        
        for table_name, config in used_tables.items():
            for mand_field in config.mandatory_fields:
                if not self._is_mandatory_field_found(mand_field, filtered_fields):
                    errors.append({
                        "field": "filterBy",
                        "message": f"Table '{table_name}' requires a filter on column '{mand_field}'"
                    })
        
        return errors

    def _collect_build_query_errors(self, params: GetDataParams) -> List[Dict]:
        """
        Collect all validation errors for a given request.
        This keeps build_query readable without changing behaviour.
        """
        all_errors: List[Dict] = []

        # 1) Validate that all referenced columns exist
        all_columns = params.get_all_columns()
        column_errors = self._validate_columns(all_columns)
        if column_errors:
            all_errors.extend(column_errors)

        # 2) Validate mandatory filters
        used_tables, column_to_table_map = self._get_explicitly_requested_tables(params)
        mandatory_errors = self._validate_mandatory_filters(params, used_tables, column_to_table_map)
        if mandatory_errors:
            all_errors.extend(mandatory_errors)

        # 3) Validate filter data types
        if params.filterBy:
            _, column_to_table_map = self._get_explicitly_requested_tables(params)
            filter_errors = self._validate_filter_data_types(params.filterBy, column_to_table_map)
            if filter_errors:
                all_errors.extend(filter_errors)

        # 4) Validate measures
        if params.measures:
            measure_errors = self._validate_measures(params.measures)
            if measure_errors:
                all_errors.extend(measure_errors)

        return all_errors

    def build_query(self, params: GetDataParams) -> Tuple[str, List[Any], str, List[Any]]:
        # Run all validations first
        all_errors = self._collect_build_query_errors(params)
        if all_errors:
            raise ValidationError(all_errors)

        # Then build the query parts
        self._reset()

        set_a_tables, column_to_table_map = self._get_explicitly_requested_tables(params)
        join_tables = self._find_tables_to_join(set_a_tables)
        main_table = self._determine_main_table(set_a_tables)

        is_aggregated = params.is_aggregated()
        self._build_select_clause(params, column_to_table_map, join_tables, is_aggregated)
        self._build_from_clause(main_table)
        self._build_join_clauses(main_table, join_tables)
        self._build_where_clause(params, column_to_table_map)
        self._build_group_by_clause(params, column_to_table_map, join_tables, is_aggregated)
        self._build_order_by_clause(params, column_to_table_map)
        self._build_pagination(params)

        main_query = self._construct_final_query()
        main_parameters = self.parameters.copy()

        count_query, count_parameters = self._build_count_query(main_table, join_tables, params)

        return main_query, main_parameters, count_query, count_parameters

    def _build_count_query(self, main_table: TableConfig, join_tables: Dict[str, TableConfig],
                            params: GetDataParams) -> Tuple[
        str, List[Any]]:
        count_parameters = []
        _, column_to_table_map = self._get_explicitly_requested_tables(params)

        if params.filterBy:
            for filter_obj in params.filterBy:
                _, params_values = self._build_filter_condition(filter_obj, column_to_table_map)
                count_parameters.extend(params_values)

        is_distinct_only = params.is_distinct_only()
        is_aggregated = params.is_aggregated()

        if self.count_strategy == "simple":
            return self._build_simple_count_query(main_table, join_tables, params, count_parameters)
        elif self.count_strategy == "distinct":
            return self._build_distinct_count_query(main_table, join_tables, params, count_parameters, is_distinct_only)
        elif self.count_strategy == "separate":
            return self._build_separate_count_query(main_table, join_tables, params, count_parameters)
        elif self.count_strategy == "estimate":
            return self._build_estimate_count_query(main_table, join_tables, params, count_parameters)
        else:
            return self._build_simple_count_query(main_table, join_tables, params, count_parameters)

    def _build_simple_count_query(self, main_table: TableConfig, join_tables: Dict[str, TableConfig],
                                  params: GetDataParams, count_parameters: List[Any]) -> Tuple[str, List[Any]]:
        count_query_parts = ["SELECT COUNT(*)"]
        count_query_parts.append(f"FROM {main_table.name}")

        for join in self.query_parts['joins']:
            count_query_parts.append(join)

        if self.query_parts['where']:
            count_query_parts.append(f"WHERE {' AND '.join(self.query_parts['where'])}")

        count_query = ' '.join(count_query_parts)
        return count_query, count_parameters

    def _build_distinct_count_query(self, main_table: TableConfig, join_tables: Dict[str, TableConfig],
                                    params: GetDataParams, count_parameters: List[Any],
                                    is_distinct_only: bool) -> Tuple[str, List[Any]]:
        _, column_to_table_map = self._get_explicitly_requested_tables(params)
        
        if is_distinct_only and params.groupBy:
            group_cols = []
            for col in params.groupBy:
                # Resolve alias to actual field name
                resolved_col = self._resolve_field_name(col, column_to_table_map)
                if '.' in resolved_col:
                    table_name, col_name = resolved_col.split('.', 1)
                    group_cols.append(col_name)
                else:
                    group_cols.append(resolved_col)

            if len(group_cols) == 1:
                count_select = f"COUNT(DISTINCT {group_cols[0]})"
            else:
                concat_cols = " || '|' || ".join(group_cols)
                count_select = f"COUNT(DISTINCT ({concat_cols}))"
        else:
            count_select = "COUNT(*)"

        count_query_parts = [f"SELECT {count_select}"]
        count_query_parts.append(f"FROM {main_table.name}")

        for join in self.query_parts['joins']:
            count_query_parts.append(join)

        if self.query_parts['where']:
            count_query_parts.append(f"WHERE {' AND '.join(self.query_parts['where'])}")

        count_query = ' '.join(count_query_parts)
        return count_query, count_parameters

    def _build_separate_count_query(self, main_table: TableConfig, join_tables: Dict[str, TableConfig],
                                    params: GetDataParams, count_parameters: List[Any]) -> Tuple[str, List[Any]]:
        _, column_to_table_map = self._get_explicitly_requested_tables(params)
        
        if params.groupBy:
            select_items = []
            for col in params.groupBy:
                # Resolve alias to actual field name
                resolved_col = self._resolve_field_name(col, column_to_table_map)
                if '.' in resolved_col:
                    table_name, col_name = resolved_col.split('.', 1)
                    select_items.append(col_name)
                else:
                    select_items.append(resolved_col)

            count_query_parts = [f"SELECT DISTINCT {', '.join(select_items)}"]
            count_query_parts.append(f"FROM {main_table.name}")

            for join in self.query_parts['joins']:
                count_query_parts.append(join)

            if self.query_parts['where']:
                count_query_parts.append(f"WHERE {' AND '.join(self.query_parts['where'])}")

            count_query = ' '.join(count_query_parts)
            return count_query, count_parameters
        else:
            return self._build_simple_count_query(main_table, join_tables, params, count_parameters)

    def _build_estimate_count_query(self, main_table: TableConfig, join_tables: Dict[str, TableConfig],
                                    params: GetDataParams, count_parameters: List[Any]) -> Tuple[str, List[Any]]:
        count_query = "SELECT -1 AS estimated_count"
        return count_query, []

    def get_count_from_results(self, count_result: List[Dict], main_results: List[Dict],
                               params: GetDataParams) -> int:
        if not count_result:
            return 0

        if self.count_strategy == "separate":
            return len(count_result)
        elif self.count_strategy == "estimate":
            if count_result[0].get('estimated_count') == -1:
                result_count = len(main_results)
                if params.page and params.page_size:
                    if result_count == params.page_size:
                        return params.page * params.page_size + params.page_size
                    else:
                        return (params.page - 1) * params.page_size + result_count
                return result_count
        else:
            count_key = next(iter(count_result[0].keys()))
            return count_result[0][count_key]

    def _reset(self):
        self.query_parts = {
            'select': [],
            'from': '',
            'joins': [],
            'where': [],
            'group_by': [],
            'order_by': '',
        }
        self.parameters = []

    def _find_table_config_by_name(self, table_name: str) -> Optional[TableConfig]:
        """
        Find a table config by name (case-insensitive).
        
        Args:
            table_name: The table name to find
            
        Returns:
            TableConfig if found, None otherwise
        """
        if table_name in self.table_configs:
            return self.table_configs[table_name]
        
        for name, config in self.table_configs.items():
            if config.name.lower() == table_name.lower():
                return config
        
        return None

    def _add_table_column_mapping(self, column: str, resolved_column: str, col_name: str, 
                                   config: TableConfig, column_to_table_map: Dict[str, TableConfig]):
        """
        Add column to table mapping for both original and resolved column names.
        
        Args:
            column: Original column name
            resolved_column: Resolved column name
            col_name: Column name (without table prefix)
            config: Table config to map to
            column_to_table_map: Dictionary to update
        """
        column_to_table_map[col_name] = config
        if column != resolved_column and '.' not in column:
            column_to_table_map[column] = config

    def _process_table_column_format(self, column: str, resolved_column: str, table_name: str, 
                                    col_name: str, set_a: Dict[str, TableConfig],
                                    column_to_table_map: Dict[str, TableConfig]):
        """
        Process a column in table.column format.
        
        Args:
            column: Original column name
            resolved_column: Resolved column name
            table_name: Table name
            col_name: Column name
            set_a: Dictionary of tables to update
            column_to_table_map: Dictionary of column mappings to update
        """
        config = self._find_table_config_by_name(table_name)
        
        if config:
            set_a[table_name] = config
            self._add_table_column_mapping(column, resolved_column, col_name, config, column_to_table_map)
        else:
            temp_config = TableConfig(table_name, 999, [])
            set_a[table_name] = temp_config
            self._add_table_column_mapping(column, resolved_column, col_name, temp_config, column_to_table_map)

    def _find_best_table_for_column(self, column_name: str) -> Optional[TableConfig]:
        """
        Find the best table (by priority) that contains the given column.
        
        Args:
            column_name: The column name to find
            
        Returns:
            Best TableConfig if found, None otherwise
        """
        best_table = None
        highest_priority = float('inf')

        for config in self.table_configs.values():
            for col_def in config.columns:
                actual_name = col_def.get('name')
                aliases = col_def.get('field_aliases', [])
                if self._matches_field_name(column_name, actual_name, aliases):
                    if config.priority < highest_priority:
                        highest_priority = config.priority
                        best_table = config
                    break

        return best_table

    def _get_actual_field_name_from_table(self, column_name: str, table_config: TableConfig) -> Optional[str]:
        """
        Get the actual field name from a table config for a given column name.
        
        Args:
            column_name: The column name (could be alias)
            table_config: The table config to search
            
        Returns:
            Actual field name if found, None otherwise
        """
        for col_def in table_config.columns:
            actual_name = col_def.get('name')
            aliases = col_def.get('field_aliases', [])
            if self._matches_field_name(column_name, actual_name, aliases):
                return actual_name
        return None

    def _process_column_only_format(self, column: str, resolved_column: str, 
                                    set_a: Dict[str, TableConfig],
                                    column_to_table_map: Dict[str, TableConfig]):
        """
        Process a column in column-only format.
        
        Args:
            column: Original column name
            resolved_column: Resolved column name
            set_a: Dictionary of tables to update
            column_to_table_map: Dictionary of column mappings to update
        """
        best_table = self._find_best_table_for_column(resolved_column)
        
        if best_table:
            set_a[best_table.name] = best_table
            actual_name = self._get_actual_field_name_from_table(resolved_column, best_table)
            if actual_name:
                column_to_table_map[actual_name] = best_table
                if column != actual_name:
                    column_to_table_map[column] = best_table

    def _get_explicitly_requested_tables(self, params: GetDataParams) -> Tuple[
        Dict[str, TableConfig], Dict[str, TableConfig]]:
        set_a = {}
        column_to_table_map = {}
        all_columns = params.get_all_columns()

        for column in all_columns:
            resolved_column = self._resolve_field_name(column)
            
            if '.' in resolved_column:
                table_name, col_name = resolved_column.split('.', 1)
                self._process_table_column_format(column, resolved_column, table_name, col_name, 
                                                 set_a, column_to_table_map)
            else:
                self._process_column_only_format(column, resolved_column, set_a, column_to_table_map)

        return set_a, column_to_table_map

    def _find_tables_to_join(self, set_a_tables: Dict[str, TableConfig]) -> Dict[str, TableConfig]:
        join_tables = dict(set_a_tables)

        for set_a_name, set_a_config in set_a_tables.items():
            all_relations = self._get_relations_for_table(set_a_config)

            for relation in all_relations:
                target_name = relation.get('name')

                target_config = None
                if target_name and target_name in self.table_configs:
                    target_config = self.table_configs[target_name]

                if target_config and target_config.name not in join_tables:
                    join_tables[target_config.name] = target_config

        for table_name, table_config in self.table_configs.items():
            if table_name in join_tables:
                continue

            has_relation_to_set_a = False
            all_relations = self._get_relations_for_table(table_config)

            for relation in all_relations:
                relation_target_name = relation.get('name')

                for set_a_name, set_a_config in set_a_tables.items():
                    if relation_target_name == set_a_config.name:
                        has_relation_to_set_a = True
                        break

                if has_relation_to_set_a:
                    break

            if has_relation_to_set_a:
                join_tables[table_name] = table_config

        return join_tables

    def _determine_main_table(self, set_a_tables: Dict[str, TableConfig]) -> TableConfig:
        if not set_a_tables:
            raise ValidationError([{
                "field": "columns",
                "message": "No tables found for requested columns"
            }])

        main_table = min(set_a_tables.values(), key=lambda x: x.priority)
        return main_table

    def _build_from_clause(self, table_config: TableConfig):
        self.query_parts['from'] = f"{table_config.name}"

    def _build_join_clauses(self, main_table: TableConfig, join_tables: Dict[str, TableConfig]):
        if not join_tables:
            return

        joined_tables = {main_table.name: main_table}

        sorted_join_tables = sorted(join_tables.values(), key=lambda x: x.priority)

        for target_table in sorted_join_tables:
            if target_table.name in joined_tables:
                continue

            join_clause = self._find_join_path(target_table, joined_tables)
            if join_clause:
                self.query_parts['joins'].append(join_clause)
                joined_tables[target_table.name] = target_table
            else:
                print(
                    f"Warning: No join path found for table {target_table.name}. This may cause ambiguity in column names.")

    def _find_join_path(self, target_table: TableConfig, joined_tables: Dict[str, TableConfig]) -> str:
        for joined_name, joined_config in joined_tables.items():
            all_relations = self._get_relations_for_table(joined_config)
            for relation in all_relations:
                relation_target_name = relation.get('name')

                if relation_target_name == target_table.name:
                    return self._build_join_clause(joined_config, target_table, relation)

            reverse_relations = self._get_reverse_relations_for_table(target_table)
            for reverse_relation in reverse_relations:
                source_name = reverse_relation.get('source_table')

                if source_name == joined_name:
                    return self._build_join_clause_from_reverse(target_table, joined_config, reverse_relation)

        return None

    def _build_join_clause(self, source_config: TableConfig, target_config: TableConfig, relation: Dict) -> str:
        join_conditions = []

        join_columns = relation.get('joinColumns', [])

        for join_col in join_columns:
            if isinstance(join_col, dict):
                if 'source' in join_col and 'target' in join_col:
                    source_col = join_col['source']
                    target_col = join_col['target']
                    condition = f"{source_config.name}.{source_col} = {target_config.name}.{target_col}"
                    join_conditions.append(condition)
                elif 'name' in join_col:
                    col_name = join_col['name']
                    condition = f"{source_config.name}.{col_name} = {target_config.name}.{col_name}"
                    join_conditions.append(condition)
            else:
                col_name = join_col
                condition = f"{source_config.name}.{col_name} = {target_config.name}.{col_name}"
                join_conditions.append(condition)

        if join_conditions:
            join_type = self._convert_join_type(relation.get('type', 'LEFT'))
            join_clause = (
                f"{join_type} JOIN {target_config.name} ON "
                f"{' AND '.join(join_conditions)}"
            )
            return join_clause

        return None

    def _build_join_clause_from_reverse(self, target_config: TableConfig, source_config: TableConfig,
                                        reverse_relation: Dict) -> str:
        join_conditions = []

        original_relation = reverse_relation.get('original_relation', {})
        join_columns = original_relation.get('joinColumns', [])

        for join_col in join_columns:
            if isinstance(join_col, dict):
                if 'source' in join_col and 'target' in join_col:
                    source_col = join_col['target']
                    target_col = join_col['source']
                    condition = f"{source_config.name}.{source_col} = {target_config.name}.{target_col}"
                    join_conditions.append(condition)
                elif 'name' in join_col:
                    col_name = join_col['name']
                    condition = f"{source_config.name}.{col_name} = {target_config.name}.{col_name}"
                    join_conditions.append(condition)
            else:
                col_name = join_col
                condition = f"{source_config.name}.{col_name} = {target_config.name}.{col_name}"
                join_conditions.append(condition)

        if join_conditions:
            join_type = self._convert_join_type(original_relation.get('type', 'LEFT'))
            join_clause = (
                f"{join_type} JOIN {target_config.name} ON "
                f"{' AND '.join(join_conditions)}"
            )
            return join_clause

        return None

    def _convert_join_type(self, relation_type: str) -> str:
        type_mapping = {
            'ONE_TO_ONE': 'LEFT',
            'ONE_TO_MANY': 'LEFT',
            'MANY_TO_ONE': 'LEFT',
            'MANY_TO_MANY': 'LEFT',
            'LEFT': 'LEFT',
            'RIGHT': 'RIGHT',
            'INNER': 'INNER',
            'OUTER': 'FULL OUTER'
        }
        return type_mapping.get(relation_type.upper(), 'LEFT')

    def _build_select_clause(self, params: GetDataParams, column_to_table_map: Dict[str, TableConfig],
                             join_tables: Dict[str, TableConfig], is_aggregated: bool):
        select_items = []
        is_distinct_only = params.is_distinct_only()
        main_table = self._determine_main_table(join_tables)

        if is_distinct_only:
            for col in params.groupBy or []:
                # Resolve alias to actual field name
                resolved_col = self._resolve_field_name(col, column_to_table_map)
                if '.' in resolved_col:
                    table_name, col_name = resolved_col.split('.', 1)
                    select_items.append(col_name)
                else:
                    select_items.append(resolved_col)
        elif is_aggregated:
            for field in main_table.mandatory_fields:
                select_items.append(f"{field}")

            for table_name, table_config in join_tables.items():
                if table_name != main_table.name:
                    for field in table_config.mandatory_fields:
                        select_items.append(f"{field}")

            for col in params.groupBy or []:
                # Resolve alias to actual field name
                resolved_col = self._resolve_field_name(col, column_to_table_map)
                if '.' in resolved_col:
                    table_name, col_name = resolved_col.split('.', 1)
                    select_items.append(col_name)
                else:
                    select_items.append(resolved_col)

            for measure in params.measures or []:
                # Resolve alias to actual field name
                col = self._resolve_field_name(measure.field, column_to_table_map)
                if '.' in col:
                    table_name, col_name = col.split('.', 1)
                    col = col_name
                alias = f"{measure.function.lower()}_{col.replace('.', '_')}"
                select_items.append(f"{measure.function.upper()}({col}) AS {alias}")

            for table_name, table_config in join_tables.items():
                for agg in table_config.aggregations:
                    agg_field = agg.get('field')
                    agg_function = agg.get('function', 'SUM').upper()
                    agg_alias = agg.get('alias', f"{agg_function.lower()}_{agg_field}")
                    # Case-insensitive matching for aggregation field
                    if any(col_def.get('name').lower() == agg_field.lower() for col_def in table_config.columns):
                        select_items.append(f"{agg_function}({agg_field}) AS {agg_alias}")
        else:
            if not params.groupBy:
                select_items = ["*"]
            else:
                all_columns = params.get_all_columns()
                for col in all_columns:
                    # Resolve alias to actual field name
                    resolved_col = self._resolve_field_name(col, column_to_table_map)
                    if '.' in resolved_col:
                        table_name, col_name = resolved_col.split('.', 1)
                        select_items.append(col_name)
                    else:
                        select_items.append(resolved_col)

        if not select_items:
            select_items = ["*"]

        self.query_parts['select'] = ['DISTINCT ' + ', '.join(select_items)] if is_distinct_only else select_items

    def _build_where_clause(self, params: GetDataParams, column_to_table_map: Dict[str, TableConfig] = None):
        if not params.filterBy:
            return

        conditions = []
        for filter_obj in params.filterBy:
            condition, params_values = self._build_filter_condition(filter_obj, column_to_table_map)
            if condition:
                conditions.append(condition)
                self.parameters.extend(params_values)

        if conditions:
            self.query_parts['where'] = [f"({' AND '.join(conditions)})"]

    def _build_filter_condition(self, filter_obj: FilterModel, column_to_table_map: Dict[str, TableConfig] = None) -> Tuple[
        str, List[Any]]:
        # Resolve alias to actual field name
        column = self._resolve_field_name(filter_obj.field, column_to_table_map)
        if '.' in column:
            table_name, col_name = column.split('.', 1)
            column = col_name

        operator = filter_obj.operator.upper()
        values = filter_obj.values

        if operator == 'BETWEEN':
            if isinstance(values, list) and len(values) == 2:
                start, end = values
                condition = f"{column} BETWEEN ? AND ?"
                return condition, [start, end]
        elif operator in ['IN', 'INLIST']:
            if isinstance(values, list) and values:
                placeholders = ','.join(['?' for _ in values])
                condition = f"{column} IN ({placeholders})"
                return condition, values
        elif operator == 'EQUAL':
            if values is not None:
                condition = f"{column} = ?"
                return condition, [values]

        return None, []

    def _has_aggregates_in_select(self) -> bool:
        """
        Check if the SELECT clause contains any aggregate functions.
        
        Returns:
            True if aggregates are found, False otherwise
        """
        aggregate_functions = {'COUNT', 'SUM', 'AVG', 'MAX', 'MIN'}
        return any(
            '(' in item and item.split('(')[0].upper() in aggregate_functions 
            for item in self.query_parts['select']
        )

    def _add_mandatory_fields_to_group_by(self, main_table: TableConfig, 
                                         join_tables: Dict[str, TableConfig],
                                         group_by_items: List[str]):
        """
        Add mandatory fields from main table and joined tables to group by items.
        
        Args:
            main_table: The main table config
            join_tables: Dictionary of joined table configs
            group_by_items: List to add fields to
        """
        for field in main_table.mandatory_fields:
            group_by_items.append(f"{field}")

        for table_name, table_config in join_tables.items():
            if table_name != main_table.name:
                for field in table_config.mandatory_fields:
                    group_by_items.append(f"{field}")

    def _add_group_by_columns(self, params: GetDataParams, column_to_table_map: Dict[str, TableConfig],
                              group_by_items: List[str]):
        """
        Add groupBy columns to group by items (resolving aliases).
        
        Args:
            params: The request parameters
            column_to_table_map: Mapping of columns to table configs
            group_by_items: List to add columns to
        """
        for col in params.groupBy or []:
            resolved_col = self._resolve_field_name(col, column_to_table_map)
            
            if '.' in resolved_col:
                _, col_name = resolved_col.split('.', 1)
                if col_name not in group_by_items:
                    group_by_items.append(col_name)
            else:
                if resolved_col not in group_by_items:
                    group_by_items.append(resolved_col)

    def _build_group_by_clause(self, params: GetDataParams, column_to_table_map: Dict[str, TableConfig],
                               join_tables: Dict[str, TableConfig], is_aggregated: bool):
        if not is_aggregated:
            return

        if not self._has_aggregates_in_select():
            return

        group_by_items = []
        main_table = self._determine_main_table(join_tables)

        self._add_mandatory_fields_to_group_by(main_table, join_tables, group_by_items)
        self._add_group_by_columns(params, column_to_table_map, group_by_items)

        if group_by_items:
            self.query_parts['group_by'] = group_by_items

    def _build_order_by_clause(self, params: GetDataParams, column_to_table_map: Dict[str, TableConfig]):
        if not params.sortBy:
            return

        order_items = []
        for sort_obj in params.sortBy:
            # Resolve alias to actual field name
            column = self._resolve_field_name(sort_obj.field, column_to_table_map)
            if '.' in column:
                table_name, col_name = column.split('.', 1)
                column = col_name
            order_items.append(f"{column} {sort_obj.order}")

        if order_items:
            self.query_parts['order_by'] = f"ORDER BY {', '.join(order_items)}"

    def _build_pagination(self, params: GetDataParams):
        if params.page and params.page_size:
            limit = params.page_size
            offset = (params.page - 1) * params.page_size
            self.query_parts['limit'] = str(limit)
            if offset > 0:
                self.query_parts['offset'] = str(offset)

    def _is_column_restricted_table_format(self, table_name: str, col_name: str) -> bool:
        """
        Check if a column in table.column format is restricted.
        
        Args:
            table_name: The table name
            col_name: The column name
            
        Returns:
            True if restricted, False otherwise
        """
        if table_name not in self.table_configs:
            return False
        
        restricted_attrs = self.table_configs[table_name].restricted_attributes
        return any(col_name.lower() == attr.lower() for attr in restricted_attrs)

    def _is_column_restricted_column_format(self, column: str, resolved_column: str,
                                           column_to_table_map: Dict[str, TableConfig]) -> bool:
        """
        Check if a column in column-only format is restricted.
        
        Args:
            column: Original column name
            resolved_column: Resolved column name
            column_to_table_map: Mapping of columns to table configs
            
        Returns:
            True if restricted, False otherwise
        """
        table_config = column_to_table_map.get(resolved_column) or column_to_table_map.get(column)
        if not table_config:
            return False
        
        restricted_attrs = table_config.restricted_attributes
        return (any(resolved_column.lower() == attr.lower() for attr in restricted_attrs) or
                any(column.lower() == attr.lower() for attr in restricted_attrs))

    def _is_column_restricted(self, column: str, resolved_column: str,
                             column_to_table_map: Dict[str, TableConfig]) -> bool:
        """
        Check if a column is restricted (handles both formats).
        
        Args:
            column: Original column name
            resolved_column: Resolved column name
            column_to_table_map: Mapping of columns to table configs
            
        Returns:
            True if restricted, False otherwise
        """
        if '.' in resolved_column:
            table_name, col_name = resolved_column.split('.', 1)
            return self._is_column_restricted_table_format(table_name, col_name)
        else:
            return self._is_column_restricted_column_format(column, resolved_column, column_to_table_map)

    def _build_distinct_query_table_format(self, table_name: str, col_name: str) -> str:
        """
        Build a distinct values query for table.column format.
        
        Args:
            table_name: The table name
            col_name: The column name
            
        Returns:
            SQL query string
        """
        return f"SELECT DISTINCT {col_name} FROM {table_name} WHERE {col_name} IS NOT NULL"

    def _build_distinct_query_column_format(self, resolved_column: str, column: str,
                                           column_to_table_map: Dict[str, TableConfig]) -> Optional[str]:
        """
        Build a distinct values query for column-only format.
        
        Args:
            resolved_column: Resolved column name
            column: Original column name
            column_to_table_map: Mapping of columns to table configs
            
        Returns:
            SQL query string if table config found, None otherwise
        """
        table_config = column_to_table_map.get(resolved_column) or column_to_table_map.get(column)
        if not table_config:
            return None
        
        return f"SELECT DISTINCT {resolved_column} FROM {table_config.name} WHERE {resolved_column} IS NOT NULL"

    def _build_distinct_query_for_column(self, column: str, resolved_column: str,
                                        column_to_table_map: Dict[str, TableConfig]) -> Optional[str]:
        """
        Build a distinct values query for a column (handles both formats).
        
        Args:
            column: Original column name
            resolved_column: Resolved column name
            column_to_table_map: Mapping of columns to table configs
            
        Returns:
            SQL query string if successful, None otherwise
        """
        if '.' in resolved_column:
            table_name, col_name = resolved_column.split('.', 1)
            return self._build_distinct_query_table_format(table_name, col_name)
        else:
            return self._build_distinct_query_column_format(resolved_column, column, column_to_table_map)

    def _process_distinct_column(self, column: str, column_to_table_map: Dict[str, TableConfig]) -> Tuple[str, str, Optional[str], List[Any]]:
        """
        Process a single column for distinct values query.
        
        Args:
            column: The column name
            column_to_table_map: Mapping of columns to table configs
            
        Returns:
            Tuple of (column, data_type, query, parameters)
        """
        resolved_column = self._resolve_field_name(column, column_to_table_map)
        data_type = self._get_column_data_type(resolved_column, column_to_table_map) or "UNKNOWN"

        if self._is_column_restricted(column, resolved_column, column_to_table_map):
            return (column, data_type, None, [])

        query = self._build_distinct_query_for_column(column, resolved_column, column_to_table_map)
        return (column, data_type, query, [])

    def build_distinct_values_query(self, columns: List[str]) -> List[Tuple[str, str, List[Any]]]:
        queries = []
        errors = self._validate_columns(columns)
        if errors:
            raise ValidationError(errors)

        _, column_to_table_map = self._get_explicitly_requested_tables(GetDataParams(groupBy=columns))

        for column in columns:
            query_tuple = self._process_distinct_column(column, column_to_table_map)
            queries.append(query_tuple)

        return queries

    def _construct_final_query(self) -> str:
        query_parts = []

        query_parts.append(f"SELECT {', '.join(self.query_parts['select'])}")
        query_parts.append(f"FROM {self.query_parts['from']}")

        for join in self.query_parts['joins']:
            query_parts.append(join)

        if self.query_parts['where']:
            query_parts.append(f"WHERE {' AND '.join(self.query_parts['where'])}")

        if self.query_parts['group_by']:
            query_parts.append(f"GROUP BY {', '.join(self.query_parts['group_by'])}")

        if self.query_parts['order_by']:
            query_parts.append(self.query_parts['order_by'])

        if 'limit' in self.query_parts and self.query_parts['limit']:
            query_parts.append(f"LIMIT {self.query_parts['limit']}")

        if 'offset' in self.query_parts and self.query_parts['offset']:
            query_parts.append(f"OFFSET {self.query_parts['offset']}")

        return ' '.join(query_parts)