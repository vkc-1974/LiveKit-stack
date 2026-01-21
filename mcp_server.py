#!/bin/env python3

# mcp_server.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import mariadb
import uvicorn
from common import settings

app = FastAPI(title="MCP Server")
host = "0.0.0.0"
port = 8000

# DB connection
conn = mariadb.connect(host=settings.db_host,
                       port=settings.db_port,
                       user=settings.db_user,
                       password=settings.db_pass,
                       database=settings.db_name)

cur = conn.cursor()

class BalanceRequest(BaseModel):
    user_id: int

@app.post("/tools/get_user_balance")
async def get_user_balance(req: BalanceRequest):
    try:
        cur.execute("SELECT balance_value FROM users WHERE user_id = ?", (req.user_id,))
        row = cur.fetchone()
        if row:
            return {"content": f"The balance of {req.user_id} user account is {row[0]}"}
        else:
            return {"content": f"There is no user account with id {req.user_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    print(f"[MCP] Start running at {host}:{port}")
    uvicorn.run(app, host=host, port=port)
