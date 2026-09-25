from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import initialize_database
from app.custom_sql import (
    QueryExecutionError,
    QueryRejectedError,
    QueryTimeoutError,
    execute_custom_sql,
)
from app.query_library import list_queries, run_query
from app.scoring import build_score_distribution, build_watchlist


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"


class CustomSqlRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=20_000)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    counts = initialize_database()
    summary = ", ".join(f"{table}={count:,}" for table, count in counts.items())
    print(f"DuckDB ready: {summary}", flush=True)
    yield


app = FastAPI(
    title="Merchant Portfolio Monitor",
    description="A synthetic-data portfolio monitoring demonstration.",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/queries")
async def available_queries() -> list[dict[str, str]]:
    return list_queries()


@app.get("/api/queries/{query_name}")
async def query_results(query_name: str) -> dict[str, object]:
    try:
        return run_query(query_name)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Query not found") from error


@app.get("/api/watchlist")
async def watchlist() -> list[dict[str, object]]:
    return build_watchlist()


@app.get("/api/watchlist/chart")
async def watchlist_chart() -> list[dict[str, int | str]]:
    return build_score_distribution()


@app.post("/api/custom-query")
def custom_query(request: CustomSqlRequest) -> dict[str, object]:
    try:
        return execute_custom_sql(request.sql)
    except QueryRejectedError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except QueryTimeoutError as error:
        raise HTTPException(status_code=408, detail=str(error)) from error
    except QueryExecutionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
