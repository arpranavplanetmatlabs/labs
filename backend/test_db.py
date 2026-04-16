from db import get_connection

conn = get_connection()
result = conn.execute(
    "INSERT INTO documents (filename, doc_type, status, extraction_status) VALUES ('test.pdf', 'tds', 'uploaded', 'processing') RETURNING id"
).fetchone()
print("Inserted doc_id:", result)
conn.close()
print("DB works!")
