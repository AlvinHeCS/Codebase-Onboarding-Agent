from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import greet, create_user, ingest_repo


@workflow.defn
class SayHelloWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        return await workflow.execute_activity(
            greet,
            name,
            schedule_to_close_timeout=timedelta(seconds=10),
        )


@workflow.defn
class CreateUserWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        greeting = await workflow.execute_activity(
            greet,
            name,
            schedule_to_close_timeout=timedelta(seconds=10),
        )
        user_id = await workflow.execute_activity(
            create_user,
            schedule_to_close_timeout=timedelta(seconds=10),
        )
        return f"Created user {user_id}. {greeting}"


@workflow.defn
class IngestRepoWorkflow:
    @workflow.run
    async def run(self, repo_url: str) -> str:
        return await workflow.execute_activity(
            ingest_repo,
            repo_url,
            start_to_close_timeout=timedelta(minutes=5),
        )
