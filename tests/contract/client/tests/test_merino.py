# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Contract tests client."""

import os
import re
import time
from typing import Any, Callable

import pytest
import requests
from kinto import (
    KintoEnvironment,
    KintoRequestAttachment,
    delete_records,
    upload_attachment,
    upload_icons,
)
from models import (
    KintoRequest,
    MerinoRequest,
    Response,
    ResponseContent,
    Service,
    Step,
    Suggestion,
    VersionResponseContent,
)
from pydantic import HttpUrl
from requests import Response as RequestsResponse

# We need to exclude the following fields on the response level:
# The request ID is dynamic in nature and the value cannot be validated here.
# The suggestions are validated separately in a different step.
CONTENT_EXCLUDE: set[str] = {"request_id", "suggestions"}

# We need to exclude the following field on the suggestion level:
# The icon URL for RS suggestions is dynamic in nature and handed to Merino by
# Kinto. We validate that in a separate step.
SUGGESTION_EXCLUDE: set[str] = {"icon"}


StepFunction = Callable[[Step], None]


@pytest.fixture(scope="session", name="merino_url")
def fixture_merino_url(request: Any) -> str:
    """Read the merino URL from the pytest config."""
    merino_url: str = request.config.option.merino_url
    return merino_url


@pytest.fixture(scope="session", name="kinto_step")
def fixture_kinto_step(
    kinto_environment: KintoEnvironment,
    kinto_attachments: dict[str, KintoRequestAttachment],
) -> StepFunction:
    """Define execution instructions for Kinto scenario step."""

    def kinto_step(step: Step) -> None:
        if type(step.request) is not KintoRequest:
            raise TypeError(
                f"Unsupported request type {type(step.request)} for Kinto service step."
            )

        attachment: KintoRequestAttachment = kinto_attachments[step.request.filename]
        record_id: str = step.request.record_id
        data_type: str = step.request.data_type
        upload_attachment(kinto_environment, record_id, attachment, data_type)

        icon_ids: set[str] = {suggestion.icon for suggestion in attachment.suggestions}
        upload_icons(kinto_environment, icon_ids)

    return kinto_step


@pytest.fixture(scope="session", name="merino_step")
def fixture_merino_step(
    merino_url: str, fetch_kinto_icon_url: Callable[[str], str]
) -> StepFunction:
    """Define execution instructions for Merino scenario step."""

    def merino_step(step: Step) -> None:
        if type(step.request) is not MerinoRequest:
            raise TypeError(
                f"Unsupported request type {type(step.request)} for Merino service "
                f"step."
            )

        if type(step.response) is not Response:
            raise TypeError(
                f"Unsupported response type {type(step.request)} for Merino service "
                f"step."
            )

        method: str = step.request.method
        url: str = f"{merino_url}{step.request.path}"
        headers: dict[str, str] = {
            header.name: header.value for header in step.request.headers
        }

        response: RequestsResponse = requests.request(method, url, headers=headers)

        error_message: str = (
            f"The expected status code is {step.response.status_code},\n"
            f"but the status code in the response is {response.status_code}.\n"
            f"The response content is '{response.text}'."
        )

        assert response.status_code == step.response.status_code, error_message

        if response.status_code == 200:
            # If the response status code is 200 OK, use the
            # assert_200_response() helper function to validate the content of
            # the response from Merino. This includes creating a pydantic model
            # instance for checking the field types and comparing a dict
            # representation of the model instance with the expected response
            # content for this step in the test scenario.

            if (
                step.request.path == "/__version__"
                and type(step.response.content) == VersionResponseContent
            ):
                assert_200_version_endpoint_response(
                    step_content=step.response.content,
                    merino_version_content=VersionResponseContent(**response.json()),
                )

            else:
                assert_200_response(
                    # type ignored to appease mypy, does not infer 2 possible types.
                    step_content=step.response.content,  # type: ignore
                    merino_content=ResponseContent(**response.json()),
                    fetch_kinto_icon_url=fetch_kinto_icon_url,
                )
            return

        if response.status_code == 204:
            # If the response status code is 204 No Content, load the response content
            # as text and compare against the value in the response model.
            assert response.text == step.response.content
            return

        # If the request to Merino was not successful, load the response
        # content into a Python dict and compare against the value in the
        # response model
        assert response.json() == step.response.content

    return merino_step


@pytest.fixture(scope="session", name="step_functions")
def fixture_step_functions(
    kinto_step: StepFunction, merino_step: StepFunction
) -> dict[Service, StepFunction]:
    """Return a dict mapping from a service name to request function."""
    return {
        Service.KINTO: kinto_step,
        Service.MERINO: merino_step,
    }


def suggestion_id(suggestion: Suggestion) -> tuple[str, int]:
    """Return the values for the fields that identify a suggestion."""
    return suggestion.provider, suggestion.block_id


def assert_200_response(
    *,
    step_content: ResponseContent,
    merino_content: ResponseContent,
    fetch_kinto_icon_url: Callable[[str], str],
) -> None:
    """Check that the content for a 200 OK response is what we expect."""
    expected_content_dict = step_content.dict(exclude=CONTENT_EXCLUDE)
    merino_content_dict = merino_content.dict(exclude=CONTENT_EXCLUDE)
    assert expected_content_dict == merino_content_dict

    # The order of suggestions in Merino's response is not guaranteed.
    # Sort them by ('provider', 'block_id') before validating them.
    sorted_merino_suggestions = [
        suggestion.dict(exclude=SUGGESTION_EXCLUDE)
        for suggestion in sorted(merino_content.suggestions, key=suggestion_id)
    ]
    sorted_expected_suggestions = [
        suggestion.dict(exclude=SUGGESTION_EXCLUDE)
        for suggestion in sorted(step_content.suggestions, key=suggestion_id)
    ]
    assert sorted_merino_suggestions == sorted_expected_suggestions

    # This is for selecting the right expected suggestion for a given Merino
    # suggestion based on the ('provider', 'block_id') fields.
    expected_suggestions_by_id = {
        suggestion_id(suggestion): suggestion for suggestion in step_content.suggestions
    }

    for suggestion in merino_content.suggestions:
        if "remote_settings" in suggestion.provider:
            # The icon URL is not static for RS suggestions
            expected_suggestion_icon: str = fetch_kinto_icon_url(suggestion.title)
            assert suggestion.icon == expected_suggestion_icon
            continue

        if "wiki_fruit" in suggestion.provider:
            # The icon URL is static for WikiFruit suggestions
            expected_suggestion = expected_suggestions_by_id[suggestion_id(suggestion)]
            assert suggestion.icon == expected_suggestion.icon
            continue


def assert_200_version_endpoint_response(
    *,
    step_content: VersionResponseContent,
    merino_version_content: VersionResponseContent,
) -> None:
    """Check that the content for a 200 OK response querying the __version__
    endpoint is what we expect.
    """
    expected_content_dict = step_content
    merino_content_dict = merino_version_content
    # Source is identitical between local dev, stage and production.
    assert expected_content_dict.source == merino_content_dict.source

    if os.environ.get("MERINO_ENV"):
        # The data in the version file is built during the CIRCLECI stage. The local dev
        # version contains placeholders. Therefore, we cannot specify the expected output
        # in scenarios, so checks made here to verify that a sha has been written, version
        # is empty and the validator worked as expected to parse build as HttpUrl.
        assert merino_content_dict.version == ""
        sha_pattern = re.compile(r"\b[0-9a-f]{40}\b")
        assert re.match(sha_pattern, merino_content_dict.commit)
        assert type(merino_content_dict.build) is HttpUrl


@pytest.fixture(scope="function", autouse=True)
def fixture_function_teardown(kinto_environment: KintoEnvironment):
    """Execute instructions after each test."""
    yield  # Allow test to execute

    delete_records(kinto_environment)


def test_merino(steps: list[Step], step_functions: dict[Service, StepFunction]) -> None:
    """Test for requesting suggestions from Merino."""
    for step in steps:
        # Process delay if defined in request model
        if (delay := step.request.delay) is not None:
            time.sleep(delay)

        step_functions[step.request.service](step)
