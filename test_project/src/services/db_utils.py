import asyncpg
import json
import uuid
from datetime import datetime

async def save_execution_to_db(execution_data: dict, triggered_by: str = "orchestrator"):
    conn = await asyncpg.connect(
        user="CLIENT_NAME_user",
        password="CLIENT_NAME_pass",
        database="CLIENT_NAME_db_new",
        host="db",
        port=5432
    )

    execution_id = str(uuid.uuid4())
    parsed_workflow_json = json.dumps(execution_data)

    await conn.execute(
        """
        INSERT INTO test_execution(
            execution_id,
            parsed_workflow_json,
            status,
            triggered_by
        )
        VALUES($1, $2, $3::exec_status, $4)
        """,
        execution_id,
        parsed_workflow_json,
        "queued",          # סטטוס התחלתי
        triggered_by
    )

    await conn.close()
    return execution_id