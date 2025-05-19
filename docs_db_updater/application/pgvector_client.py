"""
PGVector client module for the docs_db_updater application.

This module provides a client for interacting with a PostgreSQL database with the pgvector extension.
It implements the same interface as the Milvus client to allow for easy switching between the two.
This improved version includes connection pooling, reconnection logic, and retry mechanisms.
"""

import logging
import os
import random
import time
import numpy as np
import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from docs_db_updater.application import constants as const

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Maximum number of retries for database operations
MAX_RETRIES = 3
# Initial backoff time in seconds
INITIAL_BACKOFF = 1
# Maximum number of connections in the pool
MAX_CONNECTIONS = 5
# Connection timeout in seconds
CONNECTION_TIMEOUT = 30
# Query timeout in seconds
QUERY_TIMEOUT = 60

class PGVectorClient:
    """
    Client for interacting with a PostgreSQL database with the pgvector extension.
    Implements the same interface as the Milvus client to allow for easy switching.
    """

    def __init__(self):
        """
        Initialize the PGVector client with a connection pool.
        """
        # Check if connection string is provided
        if os.environ.get(const.PGVECTOR_CONNECTION_STRING):
            self.connection_string = os.environ.get(const.PGVECTOR_CONNECTION_STRING)
        else:
            # Build connection string from individual parameters
            host = os.environ.get(const.PGVECTOR_HOST, "localhost")
            port = os.environ.get(const.PGVECTOR_PORT, "5432")
            database = os.environ.get(const.PGVECTOR_DATABASE, "postgres")
            user = os.environ.get(const.PGVECTOR_USER, "postgres")
            password = os.environ.get(const.PGVECTOR_PASSWORD, "postgres")
            self.connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"

        # Create a connection pool
        self._create_pool()

        # Create the pgvector extension if it doesn't exist
        self._create_extension()

    def _create_pool(self):
        """
        Create a connection pool.
        """
        try:
            # Parse the connection string to get individual parameters
            # This is needed because psycopg2's pool doesn't accept a connection string
            if "postgresql://" in self.connection_string:
                # Remove postgresql:// prefix
                conn_str = self.connection_string.replace("postgresql://", "")

                # Split user:password@host:port/database
                user_pass, host_port_db = conn_str.split("@")

                # Split user:password
                if ":" in user_pass:
                    user, password = user_pass.split(":")
                else:
                    user = user_pass
                    password = ""

                # Split host:port/database
                if "/" in host_port_db:
                    host_port, database = host_port_db.split("/")
                else:
                    host_port = host_port_db
                    database = "postgres"

                # Split host:port
                if ":" in host_port:
                    host, port = host_port.split(":")
                else:
                    host = host_port
                    port = "5432"

                # Remove any query parameters from database
                if "?" in database:
                    database = database.split("?")[0]

                # Create the connection pool
                self.pool = pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=MAX_CONNECTIONS,
                    user=user,
                    password=password,
                    host=host,
                    port=port,
                    database=database,
                    connect_timeout=CONNECTION_TIMEOUT
                )
            else:
                # If the connection string is not in the expected format,
                # try to use it directly (though this might fail)
                self.pool = pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=MAX_CONNECTIONS,
                    dsn=self.connection_string,
                    connect_timeout=CONNECTION_TIMEOUT
                )

            logger.info("Created PostgreSQL connection pool")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise

    def _get_connection(self):
        """
        Get a connection from the pool.
        """
        try:
            conn = self.pool.getconn()
            conn.autocommit = True
            return conn
        except Exception as e:
            logger.error(f"Failed to get connection from pool: {e}")
            # Try to recreate the pool if getting a connection fails
            self._create_pool()
            # Try again
            conn = self.pool.getconn()
            conn.autocommit = True
            return conn

    def _return_connection(self, conn):
        """
        Return a connection to the pool.
        """
        try:
            # Check if the connection is still valid
            if conn and not conn.closed:
                self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"Failed to return connection to pool: {e}")
            # If returning the connection fails, try to close it
            try:
                if conn and not conn.closed:
                    conn.close()
            except:
                pass

    def _check_connection(self, conn):
        """
        Check if a connection is still valid.
        """
        try:
            # Try a simple query to check if the connection is still valid
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception:
            return False

    def _execute_with_retry(self, operation_name, operation_func, *args, **kwargs):
        """
        Execute a database operation with retry logic.

        Args:
            operation_name: Name of the operation for logging
            operation_func: Function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function

        Returns:
            The result of the operation function
        """
        retries = 0
        backoff = INITIAL_BACKOFF

        while retries < MAX_RETRIES:
            conn = None
            try:
                # Get a connection from the pool
                conn = self._get_connection()

                # Check if the connection is valid
                if not self._check_connection(conn):
                    logger.warning(f"Connection is not valid, getting a new one for {operation_name}")
                    self._return_connection(conn)
                    conn = self._get_connection()

                # Register the vector type with psycopg2
                register_vector(conn)

                # Execute the operation
                result = operation_func(conn, *args, **kwargs)

                # Return the connection to the pool
                self._return_connection(conn)

                return result
            except Exception as e:
                # Return the connection to the pool if it's still valid
                if conn:
                    try:
                        if not conn.closed:
                            # If the connection is still open but the operation failed,
                            # try to rollback any pending transaction
                            conn.rollback()
                        self._return_connection(conn)
                    except:
                        pass

                retries += 1
                logger.warning(f"Attempt {retries} for {operation_name} failed with error: {e}")

                if retries < MAX_RETRIES:
                    # Wait before retrying with exponential backoff
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    logger.error(f"All {MAX_RETRIES} retries for {operation_name} failed")
                    raise

        # This should never be reached due to the raise in the else clause above
        return None

    def _create_extension(self):
        """
        Create the pgvector extension if it doesn't exist.
        """
        def _create_extension_func(conn):
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            logger.info("Created pgvector extension")
            return True

        return self._execute_with_retry("create_extension", _create_extension_func)

    def has_collection(self, collection_name):
        """
        Check if a collection (table) exists.
        """
        def _has_collection_func(conn, collection_name):
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s);",
                    (collection_name,)
                )
                return cursor.fetchone()[0]

        try:
            return self._execute_with_retry("has_collection", _has_collection_func, collection_name)
        except Exception as e:
            logger.error(f"Failed to check if collection {collection_name} exists: {e}")
            return False

    def create_collection(self, collection_name, metric_type, schema, index_params=None):
        """
        Create a collection (table).
        """
        def _create_collection_func(conn, collection_name, metric_type, schema, index_params):
            with conn.cursor() as cursor:
                # Start with the basic table creation
                create_table_sql = f"CREATE TABLE {collection_name} ("

                # Add fields from the schema
                field_definitions = []
                primary_key = None

                for field in schema.fields:
                    field_name = field["name"]
                    field_type = self._map_datatype(field["datatype"], field.get("dim"))

                    field_def = f"{field_name} {field_type}"

                    if field.get("is_primary", False):
                        primary_key = field_name

                    field_definitions.append(field_def)

                # Add primary key constraint if specified
                if primary_key:
                    field_definitions.append(f"PRIMARY KEY ({primary_key})")

                create_table_sql += ", ".join(field_definitions)
                create_table_sql += ");"

                cursor.execute(create_table_sql)

                # Create index if index_params are provided
                if index_params:
                    for index in index_params.indexes:
                        field_name = index["field_name"]
                        index_type = index.get("index_type", "HNSW")
                        metric_type = index.get("metric_type", "L2")

                        # Map metric type to pgvector operator
                        operator = self._map_metric_type(metric_type)

                        # Create the index
                        if index_type.upper() == "HNSW":
                            cursor.execute(
                                f"CREATE INDEX ON {collection_name} USING hnsw ({field_name} {operator}) WITH (m = 16, ef_construction = 64);"
                            )
                        else:
                            # Default to IVFFlat for other index types
                            cursor.execute(
                                f"CREATE INDEX ON {collection_name} USING ivfflat ({field_name} {operator}) WITH (lists = 100);"
                            )

                logger.info(f"Created collection {collection_name}")
                return True

        try:
            return self._execute_with_retry("create_collection", _create_collection_func, collection_name, metric_type, schema, index_params)
        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            return False

    def _map_datatype(self, datatype, dim=None):
        """
        Map Milvus datatype to PostgreSQL datatype.
        """
        if datatype == "VARCHAR":
            return "VARCHAR(100)"
        elif datatype == "FLOAT_VECTOR":
            return f"vector({dim})"
        else:
            return "TEXT"

    def _map_metric_type(self, metric_type):
        """
        Map Milvus metric type to pgvector operator.
        """
        if metric_type == "L2":
            return "vector_l2_ops"
        elif metric_type == "IP" or metric_type == "INNER_PRODUCT":
            return "vector_ip_ops"
        elif metric_type == "COSINE":
            return "vector_cosine_ops"
        else:
            return "vector_l2_ops"

    def insert(self, collection_name, data):
        """
        Insert data into a collection.
        """
        def _insert_func(conn, collection_name, data):
            with conn.cursor() as cursor:
                # Get the column names from the table
                cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{collection_name}';")
                columns = [row[0] for row in cursor.fetchall()]

                # Prepare the data for insertion
                if isinstance(data, dict):
                    # Single record
                    values = []
                    for column in columns:
                        if column in data:
                            values.append(data[column])
                        else:
                            values.append(None)

                    # Insert the data
                    placeholders = ", ".join(["%s"] * len(values))
                    cursor.execute(
                        f"INSERT INTO {collection_name} ({', '.join(columns)}) VALUES ({placeholders});",
                        values
                    )
                    return {"insert_count": 1}
                else:
                    # Multiple records
                    values_list = []
                    for record in data:
                        values = []
                        for column in columns:
                            if column in record:
                                values.append(record[column])
                            else:
                                values.append(None)
                        values_list.append(values)

                    # Insert the data using execute_values for better performance
                    placeholders = ", ".join(["%s"] * len(columns))
                    execute_values(
                        cursor,
                        f"INSERT INTO {collection_name} ({', '.join(columns)}) VALUES %s;",
                        values_list
                    )
                    return {"insert_count": len(values_list)}

        try:
            return self._execute_with_retry("insert", _insert_func, collection_name, data)
        except Exception as e:
            logger.error(f"Failed to insert data into collection {collection_name}: {e}")
            return {"insert_count": 0}

    def query(self, collection_name, filter, output_fields=None):
        """
        Query data from a collection.
        """
        def _query_func(conn, collection_name, filter, output_fields):
            with conn.cursor() as cursor:
                # Build the query
                query = f"SELECT "

                if output_fields:
                    query += ", ".join(output_fields)
                else:
                    query += "*"

                query += f" FROM {collection_name} WHERE {filter};"

                cursor.execute(query)
                results = cursor.fetchall()

                # Convert results to a list of dictionaries
                if output_fields:
                    return [dict(zip(output_fields, row)) for row in results]
                else:
                    # Get column names
                    column_names = [desc[0] for desc in cursor.description]
                    return [dict(zip(column_names, row)) for row in results]

        try:
            return self._execute_with_retry("query", _query_func, collection_name, filter, output_fields)
        except Exception as e:
            logger.error(f"Failed to query data from collection {collection_name}: {e}")
            return []

    def upsert(self, collection_name, data):
        """
        Upsert data into a collection.
        """
        def _upsert_func(conn, collection_name, data):
            with conn.cursor() as cursor:
                # Get the column names from the table
                cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{collection_name}';")
                columns = [row[0] for row in cursor.fetchall()]

                # Get the primary key column
                cursor.execute(f"""
                    SELECT a.attname
                    FROM   pg_index i
                    JOIN   pg_attribute a ON a.attrelid = i.indrelid
                                        AND a.attnum = ANY(i.indkey)
                    WHERE  i.indrelid = '{collection_name}'::regclass
                    AND    i.indisprimary;
                """)
                primary_key = cursor.fetchone()

                if not primary_key:
                    # No primary key, fall back to insert
                    return self.insert(collection_name, data)

                primary_key = primary_key[0]

                # Prepare the data for upsert
                values = []
                for column in columns:
                    if column in data:
                        values.append(data[column])
                    else:
                        values.append(None)

                # Build the upsert query
                placeholders = ", ".join(["%s"] * len(values))
                update_set = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns if col != primary_key])

                cursor.execute(
                    f"""
                    INSERT INTO {collection_name} ({', '.join(columns)})
                    VALUES ({placeholders})
                    ON CONFLICT ({primary_key})
                    DO UPDATE SET {update_set};
                    """,
                    values
                )

                return {"upsert_count": 1}

        try:
            return self._execute_with_retry("upsert", _upsert_func, collection_name, data)
        except Exception as e:
            logger.error(f"Failed to upsert data into collection {collection_name}: {e}")
            return {"upsert_count": 0}

    def drop_collection(self, collection_name):
        """
        Drop a collection.
        """
        def _drop_collection_func(conn, collection_name):
            with conn.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {collection_name};")
            logger.info(f"Dropped collection {collection_name}")
            return True

        try:
            return self._execute_with_retry("drop_collection", _drop_collection_func, collection_name)
        except Exception as e:
            logger.error(f"Failed to drop collection {collection_name}: {e}")
            return False

    def describe_collection(self, collection_name):
        """
        Describe a collection.
        """
        def _describe_collection_func(conn, collection_name):
            with conn.cursor() as cursor:
                # Get the column information
                cursor.execute(f"""
                    SELECT column_name, data_type, character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = '{collection_name}';
                """)
                columns = cursor.fetchall()

                # Format the result to match Milvus client output
                fields = []
                for column in columns:
                    field = {
                        "name": column[0],
                        "type": column[1],
                    }
                    if column[2]:
                        field["max_length"] = column[2]
                    fields.append(field)

                return {"fields": fields}

        try:
            return self._execute_with_retry("describe_collection", _describe_collection_func, collection_name)
        except Exception as e:
            logger.error(f"Failed to describe collection {collection_name}: {e}")
            return {"fields": []}

    def create_schema(self, auto_id=True, enable_dynamic_field=False):
        """
        Create a schema for a collection.
        """
        return PGVectorSchema(auto_id, enable_dynamic_field)

    def prepare_index_params(self):
        """
        Prepare index parameters for a collection.
        """
        return PGVectorIndexParams()

    def close(self):
        """
        Close all connections in the pool and clean up resources.
        """
        try:
            if hasattr(self, 'pool') and self.pool:
                self.pool.closeall()
                logger.info("Closed all connections in the pool")
        except Exception as e:
            logger.error(f"Failed to close connections: {e}")

    def __del__(self):
        """
        Destructor to ensure connections are closed when the object is garbage collected.
        """
        self.close()


class PGVectorSchema:
    """
    Schema for a PGVector collection.
    """

    def __init__(self, auto_id=True, enable_dynamic_field=False):
        """
        Initialize the schema.
        """
        self.auto_id = auto_id
        self.enable_dynamic_field = enable_dynamic_field
        self.fields = []

    def add_field(self, field_name, datatype, is_primary=False, max_length=None, dim=None):
        """
        Add a field to the schema.
        """
        field = {
            "name": field_name,
            "datatype": datatype,
            "is_primary": is_primary
        }

        if max_length:
            field["max_length"] = max_length

        if dim:
            field["dim"] = dim

        self.fields.append(field)
        return self


class PGVectorIndexParams:
    """
    Index parameters for a PGVector collection.
    """

    def __init__(self):
        """
        Initialize the index parameters.
        """
        self.indexes = []

    def add_index(self, field_name, index_type, metric_type):
        """
        Add an index to the parameters.
        """
        self.indexes.append({
            "field_name": field_name,
            "index_type": index_type,
            "metric_type": metric_type
        })
        return self
