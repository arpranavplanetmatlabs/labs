import duckdb
from config import DATA_DIR, DB_PATH


def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))

    conn.execute("CREATE SEQUENCE IF NOT EXISTS doc_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS chunk_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS prop_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS ext_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS exp_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS res_id START 1")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER DEFAULT nextval('doc_id'),
            filename TEXT,
            file_path TEXT,
            file_hash TEXT,
            doc_type TEXT,
            status TEXT DEFAULT 'pending',
            extraction_status TEXT DEFAULT 'pending',
            extraction_confidence DOUBLE DEFAULT 0,
            llm_output JSON,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS scanned_folders (
            folder_path TEXT PRIMARY KEY,
            last_scanned TIMESTAMP DEFAULT NOW(),
            file_count INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER DEFAULT nextval('chunk_id'),
            doc_id INTEGER,
            content TEXT,
            page_number INTEGER,
            chunk_type TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS material_properties (
            id INTEGER DEFAULT nextval('prop_id'),
            doc_id INTEGER,
            property_name TEXT,
            value TEXT,
            unit TEXT,
            confidence DOUBLE DEFAULT 0.5,
            context TEXT,
            extraction_method TEXT DEFAULT 'llm',
            source_info TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS extraction_data (
            id INTEGER DEFAULT nextval('ext_id'),
            doc_id INTEGER,
            data_type TEXT,
            content TEXT,
            confidence DOUBLE DEFAULT 0.5,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER DEFAULT nextval('exp_id'),
            name TEXT,
            material_id INTEGER,
            material_name TEXT,
            description TEXT,
            conditions JSON,
            expected_output JSON,
            actual_output JSON,
            status TEXT DEFAULT 'pending',
            result_analysis TEXT,
            confidence_score DOUBLE DEFAULT 0,
            recommendation TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS experiment_results (
            id INTEGER DEFAULT nextval('res_id'),
            experiment_id INTEGER,
            metric_name TEXT,
            expected_value TEXT,
            actual_value TEXT,
            deviation_percent DOUBLE,
            passed BOOLEAN,
            test_method TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Check if file_hash column exists (for migration)
    try:
        conn.execute("SELECT file_hash FROM documents LIMIT 1")
    except:
        print("Migrating documents table to add file_path and file_hash...")
        conn.execute("ALTER TABLE documents ADD COLUMN file_path TEXT")
        conn.execute("ALTER TABLE documents ADD COLUMN file_hash TEXT")

    conn.close()
    print(f"Database initialized (persistence enabled): {DB_PATH}")
    return DB_PATH


def get_connection():
    return duckdb.connect(str(DB_PATH))
