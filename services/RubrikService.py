import json

import requests

import config_backup as config
from . import EmailService
from .ErrorService import BackupError
from .LoggerService import logger, LogLevel, TagLevel


_tag = TagLevel.RUBRIK
_access_token = None
_managed_volume_details = None


def _run_query(payload: dict):
    """
    Execute a GraphQL query against the Rubrik Security Cloud API.

    Validates both the HTTP response and any GraphQL errors returned
    inside an HTTP 200 response.
    """

    access_token = get_access_token()

    url = "https://crick.my.rubrik.com/api/graphql"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    response = requests.post(
        url=url,
        headers=headers,
        data=json.dumps(payload),
        timeout=60,
    )

    if response.status_code != 200:
        try:
            error_message = response.json().get(
                "message",
                response.text,
            )
        except ValueError:
            error_message = response.text

        raise BackupError(
            message=(
                "Rubrik GraphQL request failed: "
                f"HTTP {response.status_code}: {error_message}"
            ),
            tag=_tag,
        )

    response_data = response.json()

    if response_data.get("errors"):
        first_error = response_data["errors"][0]

        error_message = first_error.get(
            "message",
            "Rubrik GraphQL operation failed",
        )

        error_path = first_error.get("path", [])

        if error_path:
            error_message = (
                f"{error_message} at "
                f"{'.'.join(str(item) for item in error_path)}"
            )

        raise BackupError(
            message=f"Rubrik GraphQL error: {error_message}",
            tag=_tag,
        )

    return response_data


def get_access_token():
    """
    Obtain an access token from Rubrik Security Cloud using the
    OAuth client-credentials flow.
    """

    global _access_token

    if not _access_token:
        logger.log(
            "Requesting Access token",
            tag=_tag,
        )

        response = requests.post(
            url="https://crick.my.rubrik.com/api/client_token",
            data={
                "client_id": config.RSC_USER,
                "client_secret": config.RSC_SECRET,
                "grant_type": "client_credentials",
            },
            timeout=30,
        )

        try:
            response_data = response.json()
        except ValueError as exception:
            raise BackupError(
                message=(
                    "Access token request failed: "
                    f"Invalid JSON response: {exception}"
                ),
                tag=_tag,
            ) from exception

        if response.status_code not in (200, 201):
            error_message = response_data.get(
                "message",
                response.text,
            )

            raise BackupError(
                message=(
                    "Access token request failed: "
                    f"HTTP {response.status_code}: {error_message}"
                ),
                tag=_tag,
            )

        _access_token = response_data.get("access_token")

        if not _access_token:
            raise BackupError(
                message=(
                    "Access token request failed: "
                    "The response did not contain an access token"
                ),
                tag=_tag,
            )

        logger.log(
            "Access token generated successfully.",
            level=LogLevel.INFO,
            tag=_tag,
        )

    return _access_token


def delete_access_token():
    """
    Delete the current Rubrik Security Cloud API session.
    """

    try:
        global _access_token

        if _access_token:
            logger.log(
                "Closing Rubrik session & Deleting access token...",
                tag=_tag,
            )

            headers = {
                "Authorization": f"Bearer {_access_token}",
            }

            response = requests.delete(
                "https://crick.my.rubrik.com/api/session",
                headers=headers,
                timeout=10,
            )

            if response.status_code != 204:
                try:
                    message = response.json().get(
                        "message",
                        response.text,
                    )
                except ValueError:
                    message = response.text

                raise BackupError(
                    message=(
                        "Failed to delete access token: "
                        f"{message}"
                    ),
                    tag=_tag,
                )

            _access_token = None

            logger.log(
                "Access token deleted successfully.",
                level=LogLevel.INFO,
                tag=_tag,
            )

            logger.log(
                "Closed Rubrik session.\n\n",
                tag=_tag,
            )

    except BackupError as exception:
        exception.log_error()

        title, separator, body = exception.message.partition(":")

        if not separator:
            title = "Rubrik session error"
            body = exception.message

        EmailService.send_email(
            title=title.strip(),
            body=body.strip(),
        )

    except Exception as exception:
        error_message = f"Failed to delete access token: {exception}"

        title, separator, body = error_message.partition(":")

        if not separator:
            title = "Rubrik session error"
            body = error_message

        logger.log(
            text=error_message,
            level=LogLevel.ERROR,
            tag=_tag,
        )

        EmailService.send_email(
            title=title.strip(),
            body=body.strip(),
        )


def begin_snapshot():
    """
    Open the Rubrik Managed Volume for backup writes.
    """

    managed_volume_id = get_mv_details().get("fid")

    graphql_mutation_query = """
        mutation beginManagedVolumeSnapshot($id: String!) {
            beginManagedVolumeSnapshot(
                input: {
                    id: $id
                    config: {
                        isAsync: true
                    }
                }
            ) {
                asyncRequestStatus {
                    id
                }
            }
        }
    """

    payload = {
        "query": graphql_mutation_query,
        "operationName": "beginManagedVolumeSnapshot",
        "variables": {
            "id": managed_volume_id,
        },
    }

    try:
        logger.log(
            "Beginning snapshot...",
            tag=_tag,
        )

        _run_query(payload=payload)

        logger.log(
            "Begun Snapshot",
            tag=_tag,
        )

    except BackupError as exception:
        exception.message = (
            f"Failed to begin snapshot: {exception.message}"
        )
        raise


def end_snapshot():
    """
    End the Rubrik Managed Volume snapshot and apply its effective SLA.
    """

    try:
        global _access_token

        if _access_token:
            logger.log(
                "Ending snapshot...",
                tag=_tag,
            )

            managed_volume_details = get_mv_details()

            managed_volume_id = managed_volume_details.get("fid")

            sla_domain = (
                managed_volume_details.get("slaDomain")
                or {}
            )

            sla_id = sla_domain.get("id")

            if not sla_id:
                raise BackupError(
                    message=(
                        "Managed Volume SLA lookup failed: "
                        "No SLA ID found for "
                        f"{config.managed_volume_name}"
                    ),
                    tag=_tag,
                )

            graphql_mutation_query = """
                mutation endManagedVolumeSnapshot(
                    $id: String!
                    $slaId: String!
                ) {
                    endManagedVolumeSnapshot(
                        input: {
                            id: $id
                            params: {
                                retentionConfig: {
                                    slaId: $slaId
                                }
                            }
                        }
                    ) {
                        asyncRequestStatus {
                            id
                        }
                    }
                }
            """

            payload = {
                "query": graphql_mutation_query,
                "operationName": "endManagedVolumeSnapshot",
                "variables": {
                    "id": managed_volume_id,
                    "slaId": sla_id,
                },
            }

            _run_query(payload=payload)

            logger.log(
                "Ended Snapshot",
                tag=_tag,
            )

    except BackupError as exception:
        exception.message = (
            f"Failed to end snapshot: {exception.message}"
        )

        exception.log_error()

        title, separator, body = exception.message.partition(":")

        if not separator:
            title = "Failed to end snapshot"
            body = exception.message

        EmailService.send_email(
            title=title.strip(),
            body=body.strip(),
        )

    except Exception as exception:
        error_message = f"Failed to end snapshot: {exception}"

        title, separator, body = error_message.partition(":")

        if not separator:
            title = "Failed to end snapshot"
            body = error_message

        logger.log(
            text=error_message,
            level=LogLevel.ERROR,
            tag=_tag,
        )

        EmailService.send_email(
            title=title.strip(),
            body=body.strip(),
        )


def get_mv_details():
    """
    Retrieve a Rubrik Managed Volume by exact name.

    The modern RSC managedVolumes query returns the current Managed
    Volume ID and effective SLA domain. The result is mapped to the
    legacy internal keys expected by begin_snapshot() and end_snapshot().
    """

    global _managed_volume_details

    if _managed_volume_details is None:
        graphql_query = """
            query getManagedVolumeByName(
                $mv_name: [String!]
            ) {
                managedVolumes(
                    filter: [
                        {
                            field: NAME_EXACT_MATCH
                            texts: $mv_name
                        }
                    ]
                ) {
                    nodes {
                        id
                        name
                        effectiveSlaDomain {
                            id
                            name
                        }
                    }
                }
            }
        """

        managed_volume_name = config.managed_volume_name

        payload = {
            "query": graphql_query,
            "operationName": "getManagedVolumeByName",
            "variables": {
                "mv_name": [
                    managed_volume_name
                ],
            },
        }

        query_output = _run_query(
            payload=payload,
        )

        nodes = (
            query_output
            .get("data", {})
            .get("managedVolumes", {})
            .get("nodes", [])
        )

        if not nodes:
            raise BackupError(
                message=(
                    "Managed Volume lookup failed: "
                    "No Managed Volume found for "
                    f"{managed_volume_name}"
                ),
                tag=_tag,
            )

        managed_volume = nodes[0]

        effective_sla = (
            managed_volume.get("effectiveSlaDomain")
        )

        if (
            not effective_sla
            or not effective_sla.get("id")
        ):
            raise BackupError(
                message=(
                    "Managed Volume SLA lookup failed: "
                    "No effective SLA found for "
                    f"{managed_volume_name}"
                ),
                tag=_tag,
            )

        _managed_volume_details = {
            "fid": managed_volume["id"],
            "name": managed_volume["name"],
            "slaDomain": effective_sla,
        }

    return _managed_volume_details
