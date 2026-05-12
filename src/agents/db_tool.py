import duckdb
import pandas as pd
from crewai.tools import tool

@tool
def query_db(sql: str) -> str:
    """
    Query DuckDB database and return results as a formatted string.
    
    Args:
        sql: SQL query string to execute
        
    Returns:
        Query results as formatted string or error message
    """
    try:
        # Connect to DuckDB (relative to project root)
        con = duckdb.connect('data/risk_database.duckdb')
        
        # Execute query and fetch results as DataFrame
        result = con.execute(sql).fetchdf()
        con.close()
        
        # Convert to string for agent readability
        if result.empty:
            return "No results found."
        
        return result.to_string()
    
    except Exception as e:
        return f"❌ Database error: {str(e)}"
