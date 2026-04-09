import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.workflows import SayHelloWorkflow, CreateUserWorkflow, IngestRepoWorkflow
    from app.workflows.activities import greet, create_user, ingest_repo

async def main():
    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue="my-task-queue",
        workflows=[SayHelloWorkflow, CreateUserWorkflow, IngestRepoWorkflow],
        activities=[greet, create_user, ingest_repo],
    )
    print("Worker started.")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
