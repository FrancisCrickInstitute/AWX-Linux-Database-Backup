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
    Execute a GraphQL query against the Rubrik Security Cloud (RSC) API.

    This function retrieves an access token, sends the provided GraphQL
    payload to the RSC GraphQL endpoint, and returns the parsed JSON
    response.

    Note:
        Rubrik's GraphQL API may return HTTP 200 even when the query
        fails logically (e.g., no managed volume found). Consumers of
        this function should validate the response content, not just
        the HTTP status code.

    Args:
        payload (dict): GraphQL query and variables payload.

    Returns:
        dict: Parsed JSON response from the GraphQL API.

    Raises:
        Exception: If the HTTP request fails with a non-200 status code.
    """

    access_token = get_access_token()
    url = "https://crick.my.rubrik.com/api/graphql"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + access_token,
    }

    response = requests.post(url=url, headers=headers, data=json.dumps(payload))
    if response.status_code != 200:
        error_message = response.json().get("message", response.text)
        raise BackupError(message=error_message, tag=_tag)

    resp = response.json()

    if resp.get("errors"):
        err_path = resp.get("errors")[0].get("path")[0]
        err_message = resp.get("errors")[0].get("message")
        raise BackupError(message=f"{err_message} at {err_path}", tag=_tag)
    return resp


def get_access_token():
    """
    Obtain an access token from the Rubrik Security Cloud (RSC) API using
    client credentials.

    This function sends a POST request to the RSC client token endpoint
    with the configured client ID and client secret. On success, it
    extracts and returns the access token from the response.

    Returns:
        str: Access token string used for authenticating subsequent API calls.

    Raises:
        Exception: If the token request fails (non-200 HTTP response).
                   The error response is expected to contain a code and message.
    """
    global _access_token

    if not _access_token:
        logger.log("Requesting Access token", tag=_tag)
        response = requests.post(
            url="https://crick.my.rubrik.com/api/client_token",
            headers={"Content-Type": "application/json"},
            data=json.dumps({
                "client_id": config.RSC_USER,
                "client_secret": config.RSC_SECRET
            }),
        )

        data = response.json()
        if response.status_code != 200:
            err_msg = f"Failed to generate access token: {data.get('message')}"
            raise BackupError(err_msg, tag=_tag)
        _access_token = data.get("access_token")
        logger.log("Access token generated successfully.", level=LogLevel.INFO, tag=_tag)
    return _access_token


def delete_access_token():
    """
    Delete the current Rubrik Security Cloud (RSC) API session.

    Raises:
        Exception: If the session deletion fails.
    """
    try:
        global _access_token
        if _access_token:
            logger.log("Closing Rubrik session & Deleting access token...", tag=_tag)
            headers = {"Authorization": f"Bearer {_access_token}"}

            response = requests.delete(
                "https://crick.my.rubrik.com/api/session",
                headers=headers,
                timeout=10,
            )

            if response.status_code != 204:
                message = response.json().get("message", response.text)
                raise BackupError(
                    message=f"Failed to Delete Access token: {message}",
                    tag=_tag
                )

            logger.log("Access token deleted successfully.", level=LogLevel.INFO, tag=_tag)
            logger.log("Closed Rubrik session.\n\n", tag=_tag)
    except BackupError as ex:
        ex.log_error()
        title, body = ex.message.split(":", 1)
        EmailService.send_email(title=title, body=body)
    except Exception as ex:
        err = f"Failed to Delete Access token: {ex}"
        title, body = err.split(":", 1)
        logger.log(
            text=err,
            level=LogLevel.ERROR,
            tag=_tag,
        )
        EmailService.send_email(
            title=title,
            body=body
        )


def begin_snapshot():
    """
    Begins a snapshot for a Managed Volume in Rubrik Security Cloud.

    Returns:
        dict: GraphQL response containing the async request status ID.
    """

    fid = get_mv_details().get("fid")

    graphql_mutation_query = """
        mutation beginManagedVolumeSnapshot($id: String!){
            beginManagedVolumeSnapshot(input: {
                id: $id
                config: {isAsync: true}
            }) {
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
            "id": fid
        }
    }

    try:
        logger.log("Beginning snapshot...", tag=_tag)
        _run_query(payload=payload)
        logger.log("Begun Snapshot", tag=_tag)
    except BackupError as ex:
        ex.message = f"Failed to begin snapshot: {ex.message}"
        raise ex


def end_snapshot():
    """
    Ends a snapshot for a Managed Volume in Rubrik Security Cloud and
    apply the specified SLA domain.

    Returns:
        dict: GraphQL response containing the async request status ID.
    """
    try:
        global _access_token
        if _access_token:
            logger.log("Ending snapshot...", tag=_tag)
            fid = get_mv_details().get("fid")
            sla_id = get_mv_details().get("slaDomain").get("id")

            graphql_mutation_query = """
                      mutation endManagedVolumeSnapshot($id: String!, $slaId: String!){
                          endManagedVolumeSnapshot(
                              input: {
                                  id: $id,
                                  params: {
                                      retentionConfig: {
                                          slaId: $slaId
                                      }
                                  }
                              }
                          ){
                              asyncRequestStatus {
                                  id
                              }
                          }
                      }
                  """

            payload = {
                "query": graphql_mutation_query,
                "operationName": "endManagedVolumeSnapshot",
                "variables": {"id": fid, "slaId": sla_id}
            }

            _run_query(payload=payload)
            logger.log("Ended Snapshot", tag=_tag)
    except BackupError as ex:
        ex.message = f"Failed to end snapshot: {ex.message}"
        ex.log_error()
        title, body = ex.message.split(":", 1)
        EmailService.send_email(title=title, body=body)
    except Exception as ex:
        err = f"Failed to end snapshot: {ex}"
        title, body = err.split(":", 1)
        logger.log(
            text=err,
            level=LogLevel.ERROR,
            tag=_tag,
        )
        EmailService.send_email(
            title=title,
            body=body
        )


def get_mv_details():
    """
    Retrieve details for a Managed Volume (MV) from Rubrik Security Cloud
    by name.

    This function executes a GraphQL query to search for a Managed Volume
    matching the provided name and returns its basic details, including
    the FID and associated SLA domain.

    Returns:
        dict: Managed Volume details containing keys such as `fid`,
              `name`, and `slaDomain`.

    Raises:
        Exception: If no Managed Volume is found matching the given name.
                   Note that the underlying GraphQL API may still return
                   a successful HTTP response in this case.
    """

    global _managed_volume_details

    if _managed_volume_details is None:
        graphql_query = """
            query mv_id ($objectType: [ObjectTypeEnum!], $mv_name: String) {
                snappableConnection (filter: {objectType: $objectType, searchTerm: $mv_name}) {
                    nodes {
                        fid
                        name
                        slaDomain {
                            id
                        }
                    }
                }
            }
        """

        mv_name = config.managed_volume_name

        payload = {
            "query": graphql_query,
            "variables": {
                "objectType": "ManagedVolume",
                "mv_name": mv_name,
            },
        }

        query_output = _run_query(payload=payload)

        nodes = query_output['data']['snappableConnection']['nodes']

        if len(nodes) == 0:
            raise BackupError(
                message=f"No Managed Volume found for {mv_name}",
                tag=_tag
            )

        _managed_volume_details = nodes[0]
    return _managed_volume_details
