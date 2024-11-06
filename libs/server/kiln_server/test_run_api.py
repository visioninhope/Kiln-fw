from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.adapters.langchain_adapters import LangChainPromptAdapter
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskOutputRatingType,
    TaskRun,
)

from kiln_server.custom_errors import connect_custom_errors
from kiln_server.run_api import connect_run_api, deep_update, run_from_id


@pytest.fixture
def app():
    app = FastAPI()
    connect_run_api(app)
    connect_custom_errors(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_config():
    with patch("kiln_ai.utils.config.Config.shared") as MockConfig:
        # Mock the Config class
        mock_config_instance = MockConfig.return_value
        mock_config_instance.open_ai_api_key = "test_key"
        yield mock_config_instance


@pytest.fixture
def task_run_setup(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="This is a test instruction",
        description="This is a test task",
        parent=project,
    )
    task.save_to_file()

    run_task_request = {
        "model_name": "gpt_4o",
        "provider": "openai",
        "plaintext_input": "Test input",
    }

    task_run = TaskRun(
        parent=task,
        input="Test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "Test User"}
        ),
        output=TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "gpt_4o",
                    "model_provider": "openai",
                    "adapter_name": "kiln_langchain_adapter",
                    "prompt_builder_name": "simple_prompt_builder",
                },
            ),
        ),
    )
    task_run.save_to_file()

    return {
        "project": project,
        "task": task,
        "run_task_request": run_task_request,
        "task_run": task_run,
    }


@pytest.mark.asyncio
async def test_run_task_success(client, task_run_setup):
    project = task_run_setup["project"]
    task = task_run_setup["task"]
    run_task_request = task_run_setup["run_task_request"]

    with (
        patch("kiln_server.run_api.project_from_id") as mock_project_from_id,
        patch.object(
            LangChainPromptAdapter, "invoke", new_callable=AsyncMock
        ) as mock_invoke,
        patch("kiln_ai.utils.config.Config.shared") as MockConfig,
    ):
        mock_project_from_id.return_value = project
        mock_invoke.return_value = task_run_setup["task_run"]

        # Mock the Config class
        mock_config_instance = MockConfig.return_value
        mock_config_instance.open_ai_api_key = "test_key"

        response = client.post(
            f"/api/projects/{project.id}/tasks/{task.id}/run", json=run_task_request
        )

    assert response.status_code == 200
    res = response.json()
    assert res["output"]["output"] == "Test output"
    # Checking that the ID is not None because it's saved to the disk
    assert res["id"] is not None


@pytest.mark.asyncio
async def test_run_task_structured_output(client, task_run_setup):
    project = task_run_setup["project"]
    task = task_run_setup["task"]
    run_task_request = task_run_setup["run_task_request"]

    with (
        patch("kiln_server.run_api.project_from_id") as mock_project_from_id,
        patch.object(
            LangChainPromptAdapter, "invoke", new_callable=AsyncMock
        ) as mock_invoke,
        patch("kiln_ai.utils.config.Config.shared") as MockConfig,
    ):
        mock_project_from_id.return_value = project
        task_run = task_run_setup["task_run"]
        task_run.output.output = '{"key": "value"}'
        mock_invoke.return_value = task_run

        # Mock the Config class
        mock_config_instance = MockConfig.return_value
        mock_config_instance.open_ai_api_key = "test_key"
        mock_config_instance.user_id = "test_user"

        response = client.post(
            f"/api/projects/project1-id/tasks/{task.id}/run", json=run_task_request
        )

    res = response.json()
    assert response.status_code == 200
    assert res["output"]["output"] == '{"key": "value"}'
    # ID set because it's saved to the disk
    assert res["id"] is not None


@pytest.mark.asyncio
async def test_run_task_not_found(client, task_run_setup):
    project = task_run_setup["project"]
    run_task_request = task_run_setup["run_task_request"]

    with patch("kiln_server.run_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        response = client.post(
            "/api/projects/project1-id/tasks/non_existent_task_id/run",
            json=run_task_request,
        )

    assert response.status_code == 404
    assert response.json()["message"] == "Task not found. ID: non_existent_task_id"


@pytest.mark.asyncio
async def test_run_task_no_input(client, task_run_setup, mock_config):
    project = task_run_setup["project"]
    task = task_run_setup["task"]

    # Misisng input
    run_task_request = {"model_name": "gpt_4o", "provider": "openai"}

    with patch("kiln_server.run_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project
        response = client.post(
            f"/api/projects/project1-id/tasks/{task.id}/run", json=run_task_request
        )

    assert response.status_code == 400
    assert "No input provided" in response.json()["message"]


@pytest.mark.asyncio
async def test_run_task_structured_input(client, task_run_setup):
    project = task_run_setup["project"]
    task = task_run_setup["task"]

    with patch.object(
        Task,
        "input_schema",
        return_value={
            "type": "object",
            "properties": {"key": {"type": "string"}},
        },
    ):
        run_task_request = {
            "model_name": "gpt_4o",
            "provider": "openai",
            "structured_input": {"key": "value"},
        }

        with (
            patch("kiln_server.run_api.project_from_id") as mock_project_from_id,
            patch.object(
                LangChainPromptAdapter, "invoke", new_callable=AsyncMock
            ) as mock_invoke,
            patch("kiln_ai.utils.config.Config.shared") as MockConfig,
        ):
            mock_project_from_id.return_value = project
            mock_invoke.return_value = task_run_setup["task_run"]

            # Mock the Config class
            mock_config_instance = MockConfig.return_value
            mock_config_instance.open_ai_api_key = "test_key"
            mock_config_instance.user_id = "test_user"

            response = client.post(
                f"/api/projects/project1-id/tasks/{task.id}/run", json=run_task_request
            )

    assert response.status_code == 200
    res = response.json()
    assert res["output"]["output"] == "Test output"
    assert res["id"] is not None


def test_deep_update_with_empty_source():
    source = {}
    update = {"a": 1, "b": {"c": 2}}
    result = deep_update(source, update)
    assert result == {"a": 1, "b": {"c": 2}}


def test_deep_update_with_existing_keys():
    source = {"a": 0, "b": {"c": 1}}
    update = {"a": 1, "b": {"d": 2}}
    result = deep_update(source, update)
    assert result == {"a": 1, "b": {"c": 1, "d": 2}}


def test_deep_update_with_nested_dicts():
    source = {"a": {"b": {"c": 1}}}
    update = {"a": {"b": {"d": 2}, "e": 3}}
    result = deep_update(source, update)
    assert result == {"a": {"b": {"c": 1, "d": 2}, "e": 3}}


def test_deep_update_with_non_dict_values():
    source = {"a": 1, "b": [1, 2, 3]}
    update = {"a": 2, "b": [4, 5, 6], "c": "new"}
    result = deep_update(source, update)
    assert result == {"a": 2, "b": [4, 5, 6], "c": "new"}


def test_deep_update_with_mixed_types():
    source = {"a": 1, "b": {"c": [1, 2, 3]}}
    update = {"a": "new", "b": {"c": 4, "d": {"e": 5}}}
    result = deep_update(source, update)
    assert result == {"a": "new", "b": {"c": 4, "d": {"e": 5}}}


def test_deep_update_with_none_values():
    # Test case 1: Basic removal of keys
    source = {"a": 1, "b": 2, "c": 3}
    update = {"a": None, "b": 4}
    result = deep_update(source, update)
    assert result == {"b": 4, "c": 3}

    # Test case 2: Nested dictionaries
    source = {"x": 1, "y": {"y1": 10, "y2": 20, "y3": {"y3a": 100, "y3b": 200}}, "z": 3}
    update = {"y": {"y2": None, "y3": {"y3b": None, "y3c": 300}}, "z": None}
    result = deep_update(source, update)
    assert result == {"x": 1, "y": {"y1": 10, "y3": {"y3a": 100, "y3c": 300}}}

    # Test case 3: Update with empty dictionary
    source = {"a": 1, "b": 2}
    update = {}
    result = deep_update(source, update)
    assert result == {"a": 1, "b": 2}

    # Test case 4: Update missing with none elements
    source = {"a": 1, "b": {"d": 1}}
    update = {"b": {"e": {"f": {"h": 1, "j": None}, "g": None}}}
    result = deep_update(source, update)
    assert result == {"a": 1, "b": {"d": 1, "e": {"f": {"h": 1}}}}

    # Test case 5: Mixed types
    source = {"a": 1, "b": {"x": 10, "y": 20}, "c": [1, 2, 3]}
    update = {"b": {"y": None, "z": 30}, "c": None, "d": 4}
    result = deep_update(source, update)
    assert result == {"a": 1, "b": {"x": 10, "z": 30}, "d": 4}

    # Test case 6: Update with
    source = {}
    update = {"a": {"b": None, "c": None}}
    result = deep_update(source, update)
    assert result == {"a": {}}

    # Test case 7: Update with
    source = {
        "output": {
            "rating": None,
            "model_type": "task_output",
        },
    }
    update = {
        "output": {
            "rating": {
                "value": 2,
                "type": "five_star",
                "requirement_ratings": {
                    "148753630565": None,
                    "988847661375": 3,
                    "474350686960": None,
                },
            }
        }
    }
    result = deep_update(source, update)
    assert result["output"]["rating"]["value"] == 2
    assert result["output"]["rating"]["type"] == "five_star"
    assert result["output"]["rating"]["requirement_ratings"] == {
        # "148753630565": None,
        "988847661375": 3,
        # "474350686960": None,
    }


def test_update_run_method():
    run = TaskRun(
        input="Test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "Jane Doe"}
        ),
        output=TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.human, properties={"created_by": "Jane Doe"}
            ),
        ),
    )

    dumped = run.model_dump()
    merged = deep_update(dumped, {"input": "Updated input"})
    updated_run = TaskRun.model_validate(merged)
    assert updated_run.input == "Updated input"

    update = {
        "output": {"rating": {"value": 4, "type": TaskOutputRatingType.five_star}}
    }
    dumped = run.model_dump()
    merged = deep_update(dumped, update)
    updated_run = TaskRun.model_validate(merged)
    assert updated_run.output.rating.value == 4
    assert updated_run.output.rating.type == TaskOutputRatingType.five_star


@pytest.mark.asyncio
async def test_update_run(client, tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()
    task = Task(
        name="Test Task",
        instruction="This is a test instruction",
        description="This is a test task",
        parent=project,
    )
    task.save_to_file()
    run = TaskRun(
        parent=task,
        input="Test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "Jane Doe"}
        ),
        output=TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.human, properties={"created_by": "Jane Doe"}
            ),
        ),
    )
    run.save_to_file()

    test_cases = [
        {
            "name": "Update output rating",
            "patch": {
                "output": {
                    "rating": {"value": 4, "type": TaskOutputRatingType.five_star},
                }
            },
            "expected": {
                "output": {
                    "rating": {"value": 4, "type": TaskOutputRatingType.five_star},
                }
            },
        },
        {
            "name": "Update input",
            "patch": {
                "input": "Updated input",
            },
            "expected": {
                "input": "Updated input",
            },
        },
    ]

    for case in test_cases:
        with patch("kiln_server.run_api.project_from_id") as mock_project_from_id:
            mock_project_from_id.return_value = project

            response = client.patch(
                f"/api/projects/project1-id/tasks/{task.id}/runs/{run.id}",
                json=case["patch"],
            )

            assert response.status_code == 200, f"Failed on case: {case['name']}"

    # Test error cases, including deep validation
    error_cases = [
        {
            "name": "Task not found",
            "task_id": "non_existent_task_id",
            "run_id": run.id,
            "expected_status": 404,
            "expected_detail": "Task not found. ID: non_existent_task_id",
            "updates": {"input": "Updated input"},
        },
        {
            "name": "Run not found",
            "task_id": task.id,
            "run_id": "non_existent_run_id",
            "expected_status": 404,
            "expected_detail": "Run not found. ID: non_existent_run_id",
            "updates": {"input": "Updated input"},
        },
        {
            "name": "Invalid input",
            "task_id": task.id,
            "run_id": run.id,
            "expected_status": 422,
            "expected_detail": "Input: Input should be a valid string",
            "updates": {"input": 123},
        },
        {
            "name": "Invalid rating without value",
            "task_id": task.id,
            "run_id": run.id,
            "expected_status": 422,
            "expected_detail": "Output.Rating.Type: Input should be 'five_star' or 'custom'",
            "updates": {
                "output": {
                    "rating": {"type": "invalid", "rating": 1},
                }
            },
        },
    ]

    for case in error_cases:
        with patch("kiln_server.run_api.project_from_id") as mock_project_from_id:
            mock_project_from_id.return_value = project

            response = client.patch(
                f"/api/projects/project1-id/tasks/{case['task_id']}/runs/{case['run_id']}",
                json=case["updates"],
            )

            assert (
                response.status_code == case["expected_status"]
            ), f"Failed on case: {case['name']}"
            assert (
                response.json()["message"] == case["expected_detail"]
            ), f"Failed on case: {case['name']}"


@pytest.fixture
def test_run(tmp_path) -> TaskRun:
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()
    task = Task(
        name="Test Task",
        instruction="This is a test instruction",
        description="This is a test task",
        parent=project,
    )
    task.save_to_file()
    run = TaskRun(
        parent=task,
        input="Test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "Jane Doe"}
        ),
        output=TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.human, properties={"created_by": "Jane Doe"}
            ),
        ),
    )
    run.save_to_file()
    return run


def test_run_from_id_success(test_run):
    with patch("kiln_server.run_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = test_run.parent
        result = run_from_id(test_run.parent.parent.id, test_run.parent.id, test_run.id)
        assert result.id == test_run.id
        assert result.input == "Test input"
        assert result.output.output == "Test output"


def test_run_from_id_not_found(test_run):
    with patch("kiln_server.run_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = test_run.parent
        with pytest.raises(HTTPException) as exc_info:
            run_from_id(
                test_run.parent.parent.id, test_run.parent.id, "non_existent_run_id"
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Run not found. ID: non_existent_run_id"


async def test_get_run_success(client, test_run):
    with patch("kiln_server.run_api.run_from_id") as mock_run_from_id:
        mock_run_from_id.return_value = test_run
        response = client.get(
            f"/api/projects/{test_run.parent.parent.id}/tasks/{test_run.parent.id}/runs/{test_run.id}"
        )

    assert response.status_code == 200
    result = response.json()
    assert result["id"] == test_run.id
    assert result["input"] == "Test input"
    assert result["output"]["output"] == "Test output"


async def test_get_run_not_found(client):
    with patch("kiln_server.run_api.run_from_id") as mock_run_from_id:
        mock_run_from_id.side_effect = HTTPException(
            status_code=404, detail="Run not found"
        )
        response = client.get(
            "/api/projects/project1-id/tasks/task1-id/runs/non_existent_run_id"
        )

    assert response.status_code == 404
    assert response.json()["message"] == "Run not found"


@pytest.mark.asyncio
async def test_get_runs_success(client, task_run_setup):
    project = task_run_setup["project"]
    task = task_run_setup["task"]
    task_run = task_run_setup["task_run"]

    with patch("kiln_server.run_api.task_from_id") as mock_task_from_id:
        mock_task = MagicMock()
        mock_task.runs.return_value = [task_run]
        mock_task_from_id.return_value = mock_task

        response = client.get(f"/api/projects/{project.id}/tasks/{task.id}/runs")

    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == task_run.id
    assert result[0]["input"] == "Test input"
    assert result[0]["output"]["output"] == "Test output"


@pytest.mark.asyncio
async def test_get_runs_empty(client, task_run_setup):
    project = task_run_setup["project"]
    task = task_run_setup["task"]

    with patch("kiln_server.run_api.task_from_id") as mock_task_from_id:
        mock_task = MagicMock()
        mock_task.runs.return_value = []
        mock_task_from_id.return_value = mock_task

        response = client.get(f"/api/projects/{project.id}/tasks/{task.id}/runs")

    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, list)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_get_runs_task_not_found(client):
    with patch("kiln_server.run_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.side_effect = HTTPException(
            status_code=404, detail="Task not found"
        )
        response = client.get(
            "/api/projects/project1-id/tasks/non_existent_task_id/runs"
        )

    assert response.status_code == 404
    assert response.json()["message"] == "Task not found"


@pytest.mark.asyncio
async def test_delete_run(client, task_run_setup):
    project = task_run_setup["project"]
    task = task_run_setup["task"]
    task_run = task_run_setup["task_run"]

    # Verify the run file exists before deletion
    path = task_run.path
    assert path.exists()
    assert path.is_file()
    assert path.parent.exists()

    with patch("kiln_server.run_api.run_from_id") as mock_run_from_id:
        mock_run_from_id.return_value = task_run
        response = client.delete(
            f"/api/projects/{project.id}/tasks/{task.id}/runs/{task_run.id}"
        )

    assert response.status_code == 200
    # Verify the file was actually deleted
    assert not path.exists()
    assert not path.parent.exists()
    # Don't delete the task directory
    assert path.parent.parent.exists()


@pytest.mark.asyncio
async def test_delete_run_not_found(client, task_run_setup):
    project = task_run_setup["project"]
    task = task_run_setup["task"]

    with patch("kiln_server.run_api.task_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = task

        response = client.delete(
            f"/api/projects/{project.id}/tasks/{task.id}/runs/non_existent_run_id"
        )

    assert response.status_code == 404
    assert response.json()["message"] == "Run not found. ID: non_existent_run_id"


@pytest.mark.asyncio
async def test_update_run_clear_repair_fields(client, task_run_setup):
    project = task_run_setup["project"]
    task = task_run_setup["task"]

    run = TaskRun(
        parent=task,
        input="Test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "Jane Doe"}
        ),
        output=TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.human, properties={"created_by": "Jane Doe"}
            ),
        ),
        repair_instructions="Fix this output",
        repaired_output=TaskOutput(
            output="Fixed output",
            source=DataSource(
                type=DataSourceType.human, properties={"created_by": "Jane Doe"}
            ),
        ),
    )

    run.save_to_file()
    assert run.repair_instructions is not None
    assert run.repaired_output is not None

    # Patch to clear repair fields
    patch_data = {"output": {"repair_instruction": None, "repaired_output": None}}

    with patch("kiln_server.run_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project

        response = client.patch(
            f"/api/projects/project1-id/tasks/{task.id}/runs/{run.id}",
            json=patch_data,
        )

        assert response.status_code == 200
        result = response.json()

        # Verify repair fields are removed but other fields remain
        assert "repair_instruction" not in result["output"]
        assert "repaired_output" not in result["output"]
        assert result["output"]["output"] == "Test output"
        assert result["input"] == "Test input"