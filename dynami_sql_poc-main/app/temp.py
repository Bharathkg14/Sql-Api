def _build_count_query(self, main_table: TableConfig, join_tables: Dict[str, TableConfig],
                       params: GetDataParams) -> Tuple[str, List[Any]]:
    count_parameters = self.parameters.copy()  # Reuse main params (from WHERE)

    # Build the inner query: same as main but without ORDER BY, LIMIT, OFFSET
    inner_parts = []
    select_clause = f"SELECT {', '.join(self.query_parts['select'])}"
    inner_parts.append(select_clause)
    inner_parts.append(f"FROM {self.query_parts['from']}")
    for join in self.query_parts['joins']:
        inner_parts.append(join)
    if self.query_parts['where']:
        inner_parts.append(f"WHERE {' AND '.join(self.query_parts['where'])}")
    if self.query_parts['group_by']:
        inner_parts.append(f"GROUP BY {', '.join(self.query_parts['group_by'])}")

    inner_query = ' '.join(inner_parts)

    # Wrap in count subquery
    count_query = f"SELECT COUNT(*) as count FROM ({inner_query}) as subquery"

    return count_query, count_parameters